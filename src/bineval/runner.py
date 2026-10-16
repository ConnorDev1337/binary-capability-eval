"""The runner interface and the evaluation loop.

bineval does not ship an agent. You implement :class:`AgentRunner` for your own model and
your own isolated sandbox; :func:`evaluate` calls it ``k`` times per challenge, grades each
submission with the challenge's grader, and returns :class:`Attempt` records.

The grader, not the runner, decides whether an attempt is solved. The runner only reports
its submission and how far it believes it got; :func:`evaluate` reconciles that claim with
the grade so a runner cannot inflate its own score.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from bineval.challenge import Challenge
from bineval.grader import grade
from bineval.rubric import Attempt, RubricStep


@dataclass(frozen=True)
class RunOutput:
    """What a runner returns for one run.

    ``furthest_step`` is the runner's (or an annotator's) judgement of how far the
    attempt progressed. It is advisory: :func:`evaluate` overrides it with ``DELIVER``
    when the grader accepts the submission and caps it below ``DELIVER`` when it does not.
    """

    submission: str
    furthest_step: RubricStep = RubricStep.NONE
    notes: str = ""


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


def evaluate(
    challenges: Iterable[Challenge],
    runner: AgentRunner,
    *,
    k: int = 3,
    on_attempt: Callable[[Attempt], None] | None = None,
) -> list[Attempt]:
    """Run every challenge ``k`` times and return graded attempts.

    *on_attempt* is called after each attempt, so a caller can append it to a JSONL log
    immediately rather than holding everything in memory until the end.
    """

    if k < 1:
        raise ValueError("k must be >= 1")
    attempts: list[Attempt] = []
    for ch in challenges:
        for i in range(k):
            out = runner.run(ch, i)
            outcome = grade(ch.grader, out.submission)
            attempt = Attempt(
                challenge_id=ch.id,
                level=ch.level.value,
                model=runner.model,
                run_index=i,
                solved=outcome.correct,
                furthest_step=reconcile_step(out.furthest_step, outcome.correct),
                notes=out.notes,
                tags=ch.tags,
            )
            attempts.append(attempt)
            if on_attempt is not None:
                on_attempt(attempt)
    return attempts
