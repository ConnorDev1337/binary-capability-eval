"""The runner interface and the evaluation loop.

bineval does not ship an agent. You implement :class:`AgentRunner` for your own model and
your own isolated sandbox; :func:`evaluate` calls it ``k`` times per challenge, grades each
submission with the challenge's grader, and returns :class:`Attempt` records.

The grader, not the runner, decides whether an attempt is solved. The runner only reports
its submission, why the attempt ended, and how far it believes it got; :func:`evaluate`
reconciles those claims with the grade so a runner cannot inflate its own score. When a
challenge defines checkpoints, the step comes from grading them and the claim is ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from bineval.challenge import Challenge
from bineval.grader import grade
from bineval.rubric import Attempt, RubricStep, StepSource, StopReason

# Exception text goes into the attempt's notes; keep it short so a log never carries a
# transcript fragment by accident.
_MAX_ERROR_NOTE = 200


@dataclass(frozen=True)
class RunOutput:
    """What a runner returns for one run.

    ``furthest_step`` is the runner's (or an annotator's) judgement of how far the
    attempt progressed. It is advisory: :func:`evaluate` overrides it with ``DELIVER``
    when the grader accepts the submission and caps it below ``DELIVER`` when it does not.
    For a challenge with checkpoints it is ignored in favour of ``checkpoint_answers``,
    keyed by checkpoint id, whenever any are given. Include every checkpoint you asked,
    with an empty string if the agent gave no answer, so an unanswered question counts
    as failed rather than unasked.

    ``stop_reason`` says why the attempt ended. Report ``INFRA_ERROR`` for failures that
    are not the model's (API errors, sandbox crashes); those attempts are excluded from
    the metrics and re-run on resume.
    """

    submission: str
    furthest_step: RubricStep = RubricStep.NONE
    notes: str = ""
    stop_reason: StopReason = StopReason.ANSWERED
    checkpoint_answers: Mapping[str, str] = field(default_factory=dict)


class AgentRunner(Protocol):
    """Implement this for your model and sandbox."""

    model: str

    def run(self, challenge: Challenge, run_index: int) -> RunOutput: ...


def reconcile_step(claimed: RubricStep, correct: bool) -> RubricStep:
    """Make the recorded step consistent with the grade."""

    if correct:
        return RubricStep.DELIVER
    if claimed is RubricStep.DELIVER:
        return RubricStep.BUILD_SOLUTION
    return claimed


def checkpoint_step(challenge: Challenge, answers: Mapping[str, str]) -> RubricStep:
    """The furthest step evidenced by a passing checkpoint, or ``NONE``."""

    passed = [
        cp.step
        for cp in challenge.checkpoints
        if cp.id in answers and grade(cp.grader, answers[cp.id]).correct
    ]
    return max(passed, default=RubricStep.NONE)


def grade_run(challenge: Challenge, model: str, run_index: int, out: RunOutput) -> Attempt:
    """Turn one :class:`RunOutput` into a graded, reconciled :class:`Attempt`."""

    correct = grade(challenge.grader, out.submission).correct
    # No answers at all means the runner did not ask the questions, which is "not
    # measured", not "failed every checkpoint". Fall back to the claim in that case.
    if challenge.checkpoints and out.checkpoint_answers:
        claimed = checkpoint_step(challenge, out.checkpoint_answers)
        source = StepSource.CHECKPOINTS
    else:
        claimed = out.furthest_step
        source = StepSource.CLAIMED
    return Attempt(
        challenge_id=challenge.id,
        level=challenge.level.value,
        model=model,
        run_index=run_index,
        solved=correct,
        furthest_step=reconcile_step(claimed, correct),
        notes=out.notes,
        tags=challenge.tags,
        # An accepted answer is an answer, whatever the runner said about how it ended.
        stop_reason=StopReason.ANSWERED if correct else out.stop_reason,
        step_source=source,
        human_minutes=challenge.human_minutes,
    )


def _error_attempt(challenge: Challenge, model: str, run_index: int, exc: Exception) -> Attempt:
    note = f"runner raised {type(exc).__name__}: {exc}"
    if len(note) > _MAX_ERROR_NOTE:
        note = note[: _MAX_ERROR_NOTE - 3] + "..."
    return Attempt(
        challenge_id=challenge.id,
        level=challenge.level.value,
        model=model,
        run_index=run_index,
        solved=False,
        furthest_step=RubricStep.NONE,
        notes=note,
        tags=challenge.tags,
        stop_reason=StopReason.INFRA_ERROR,
        human_minutes=challenge.human_minutes,
    )


def evaluate(
    challenges: Iterable[Challenge],
    runner: AgentRunner,
    *,
    k: int = 3,
    on_attempt: Callable[[Attempt], None] | None = None,
    done: Iterable[Attempt] = (),
) -> list[Attempt]:
    """Run every challenge ``k`` times and return the new graded attempts.

    *on_attempt* is called after each attempt, so a caller can append it to a JSONL log
    immediately rather than holding everything in memory until the end.

    *done* is a previous log to resume from: a run already recorded for this runner's model
    is skipped, unless it ended in ``INFRA_ERROR``, in which case it is run again. Only the
    new attempts are returned.

    An exception from the runner is recorded as an ``INFRA_ERROR`` attempt and the loop
    moves on, so one crashed sandbox does not end the whole evaluation.
    """

    if k < 1:
        raise ValueError("k must be >= 1")
    finished = {
        (a.challenge_id, a.run_index) for a in done if a.model == runner.model and a.counted
    }
    attempts: list[Attempt] = []
    for ch in challenges:
        for i in range(k):
            if (ch.id, i) in finished:
                continue
            try:
                # Grading is inside the try too: a runner that returns a malformed
                # RunOutput has failed this run, and the rest of the evaluation still runs.
                attempt = grade_run(ch, runner.model, i, runner.run(ch, i))
            except Exception as exc:
                attempt = _error_attempt(ch, runner.model, i, exc)
            attempts.append(attempt)
            if on_attempt is not None:
                on_attempt(attempt)
    return attempts
