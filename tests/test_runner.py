from __future__ import annotations

import pytest

from bineval.challenge import Challenge, GraderKind, GraderSpec, Level
from bineval.rubric import RubricStep
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
