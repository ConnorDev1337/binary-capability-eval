from __future__ import annotations

import pytest

from bineval.challenge import Challenge, Checkpoint, GraderKind, GraderSpec, Level
from bineval.rubric import Attempt, RubricStep, StepSource, StopReason
from bineval.runner import RunOutput, evaluate, reconcile_step


def _challenge(cid: str = "c1") -> Challenge:
    return Challenge(
        id=cid,
        level=Level.ASM_READING,
        title="t",
        grader=GraderSpec(GraderKind.EXACT, "right"),
        tags=("demo",),
    )


class ScriptedRunner:
    """Returns pre-set outputs in order; stands in for a real agent."""

    model = "scripted"

    def __init__(self, outputs: list[RunOutput]) -> None:
        self._outputs = iter(outputs)
        self.calls: list[tuple[str, int]] = []

    def run(self, challenge: Challenge, run_index: int) -> RunOutput:
        self.calls.append((challenge.id, run_index))
        return next(self._outputs)


def test_reconcile_step():
    assert reconcile_step(RubricStep.NONE, True) is RubricStep.DELIVER
    assert reconcile_step(RubricStep.DELIVER, False) is RubricStep.BUILD_SOLUTION
    assert reconcile_step(RubricStep.LOCATE_FLAW, False) is RubricStep.LOCATE_FLAW


def test_evaluate_runs_k_times_and_grades():
    runner = ScriptedRunner(
        [
            RunOutput("right", RubricStep.READ_ASSEMBLY),
            RunOutput("wrong", RubricStep.DELIVER),
            RunOutput("wrong", RubricStep.REASON_MEMORY, notes="ran out of turns"),
        ]
    )
    attempts = evaluate([_challenge()], runner, k=3)

    assert runner.calls == [("c1", 0), ("c1", 1), ("c1", 2)]
    assert [a.solved for a in attempts] == [True, False, False]
    # The grader, not the runner, decides DELIVER.
    assert [a.furthest_step for a in attempts] == [
        RubricStep.DELIVER,
        RubricStep.BUILD_SOLUTION,
        RubricStep.REASON_MEMORY,
    ]
    assert attempts[2].notes == "ran out of turns"
    assert all(a.model == "scripted" and a.level == "ASM_READING" for a in attempts)
    assert all(a.tags == ("demo",) for a in attempts)


def test_evaluate_streams_attempts():
    runner = ScriptedRunner([RunOutput("right"), RunOutput("right")])
    seen = []
    evaluate([_challenge("a"), _challenge("b")], runner, k=1, on_attempt=seen.append)
    assert [a.challenge_id for a in seen] == ["a", "b"]


def test_evaluate_rejects_bad_k():
    with pytest.raises(ValueError, match="k"):
        evaluate([_challenge()], ScriptedRunner([]), k=0)


class RaisingRunner:
    model = "flaky"

    def __init__(self, fail_on: set[int]) -> None:
        self.fail_on = fail_on

    def run(self, challenge: Challenge, run_index: int) -> RunOutput:
        if run_index in self.fail_on:
            raise TimeoutError("sandbox did not answer " + "x" * 500)
        return RunOutput("right")


def test_runner_exception_is_recorded_and_loop_continues():
    attempts = evaluate([_challenge()], RaisingRunner({1}), k=3)
    assert [a.stop_reason for a in attempts] == [
        StopReason.ANSWERED,
        StopReason.INFRA_ERROR,
        StopReason.ANSWERED,
    ]
    failed = attempts[1]
    assert not failed.solved and not failed.counted
    assert failed.furthest_step is RubricStep.NONE
    assert failed.notes.startswith("runner raised TimeoutError")
    assert len(failed.notes) <= 200


def test_malformed_output_is_an_infra_error():
    runner = ScriptedRunner([RunOutput(123)])  # type: ignore[arg-type]
    (attempt,) = evaluate([_challenge()], runner, k=1)
    assert attempt.stop_reason is StopReason.INFRA_ERROR


def test_resume_skips_done_and_reruns_infra_errors():
    def done_attempt(run: int, stop: StopReason, model: str = "scripted") -> Attempt:
        return Attempt("c1", "ASM_READING", model, run, False, RubricStep.NONE, stop_reason=stop)

    done = [
        done_attempt(0, StopReason.ANSWERED),
        done_attempt(1, StopReason.INFRA_ERROR),
        done_attempt(2, StopReason.ANSWERED, model="other-model"),
    ]
    runner = ScriptedRunner([RunOutput("right"), RunOutput("right")])
    new = evaluate([_challenge()], runner, k=3, done=done)
    assert runner.calls == [("c1", 1), ("c1", 2)]
    assert [a.run_index for a in new] == [1, 2]


def test_stop_reason_passes_through_unless_solved():
    runner = ScriptedRunner(
        [
            RunOutput("", stop_reason=StopReason.REFUSED),
            RunOutput("right", stop_reason=StopReason.BUDGET_EXHAUSTED),
        ]
    )
    refused, solved = evaluate([_challenge()], runner, k=2)
    assert refused.stop_reason is StopReason.REFUSED and not refused.solved
    # The grader owns the outcome: an accepted answer was an answer.
    assert solved.stop_reason is StopReason.ANSWERED and solved.solved


def _checkpointed() -> Challenge:
    return Challenge(
        id="cp",
        level=Level.VULN_DETECTION,
        title="t",
        grader=GraderSpec(GraderKind.EXACT, "right"),
        human_minutes=20,
        checkpoints=(
            Checkpoint(
                "size", RubricStep.REASON_MEMORY, "buffer size?", GraderSpec(GraderKind.EXACT, "64")
            ),
            Checkpoint(
                "func",
                RubricStep.LOCATE_FLAW,
                "which function?",
                GraderSpec(GraderKind.EXACT, "parse"),
            ),
        ),
    )


def test_checkpoints_decide_the_step_and_ignore_the_claim():
    runner = ScriptedRunner(
        [
            RunOutput("wrong", RubricStep.BUILD_SOLUTION, checkpoint_answers={"size": "64"}),
            RunOutput("wrong", RubricStep.BUILD_SOLUTION, checkpoint_answers={"func": "parse"}),
            RunOutput("wrong", RubricStep.BUILD_SOLUTION, checkpoint_answers={"size": "32"}),
            RunOutput("right", RubricStep.NONE, checkpoint_answers={"size": ""}),
        ]
    )
    attempts = evaluate([_checkpointed()], runner, k=4)
    assert [a.furthest_step for a in attempts] == [
        RubricStep.REASON_MEMORY,
        # Furthest, not final: a later step counts without the earlier checkpoint.
        RubricStep.LOCATE_FLAW,
        RubricStep.NONE,
        RubricStep.DELIVER,
    ]
    assert all(a.step_source is StepSource.CHECKPOINTS for a in attempts)
    assert all(a.human_minutes == 20 for a in attempts)


def test_checkpoints_without_answers_fall_back_to_the_claim():
    runner = ScriptedRunner([RunOutput("wrong", RubricStep.LOCATE_FLAW)])
    (attempt,) = evaluate([_checkpointed()], runner, k=1)
    assert attempt.furthest_step is RubricStep.LOCATE_FLAW
    assert attempt.step_source is StepSource.CLAIMED


def test_claimed_steps_are_marked_claimed():
    (attempt,) = evaluate([_challenge()], ScriptedRunner([RunOutput("wrong")]), k=1)
    assert attempt.step_source is StepSource.CLAIMED
