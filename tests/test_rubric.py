from __future__ import annotations

import pytest

from bineval.rubric import Attempt, RubricStep, StepSource, StopReason


def test_steps_are_ordered():
    assert list(RubricStep) == sorted(RubricStep)
    assert RubricStep.NONE < RubricStep.READ_ASSEMBLY < RubricStep.DELIVER


def test_every_step_has_label():
    for step in RubricStep:
        assert step.label


def test_solved_must_reach_deliver():
    with pytest.raises(ValueError, match="DELIVER"):
        Attempt("c", "ASM_READING", "m", 0, True, RubricStep.BUILD_SOLUTION)


def test_unsolved_cannot_reach_deliver():
    with pytest.raises(ValueError, match="DELIVER"):
        Attempt("c", "ASM_READING", "m", 0, False, RubricStep.DELIVER)


def test_negative_run_index():
    with pytest.raises(ValueError, match="run_index"):
        Attempt("c", "ASM_READING", "m", -1, False, RubricStep.NONE)


def test_round_trip():
    a = Attempt("c", "VULN_DETECTION", "m", 2, False, RubricStep.LOCATE_FLAW, "n", ("t",))
    assert Attempt.from_dict(a.to_dict()) == a


@pytest.mark.parametrize("step", ["locate_flaw", "LOCATE_FLAW", 3])
def test_from_dict_step_forms(step):
    a = Attempt.from_dict(
        {
            "challenge_id": "c",
            "level": "ASM_READING",
            "model": "m",
            "run_index": 0,
            "solved": False,
            "furthest_step": step,
        }
    )
    assert a.furthest_step is RubricStep.LOCATE_FLAW


def test_from_dict_unknown_step():
    with pytest.raises(ValueError, match="unknown rubric step"):
        Attempt.from_dict(
            {
                "challenge_id": "c",
                "level": "ASM_READING",
                "model": "m",
                "run_index": 0,
                "solved": False,
                "furthest_step": "GUESS",
            }
        )


def test_from_dict_missing_fields():
    with pytest.raises(ValueError, match="missing"):
        Attempt.from_dict({"challenge_id": "c"})


def test_round_trip_with_new_fields():
    a = Attempt(
        "c",
        "VULN_DETECTION",
        "m",
        0,
        False,
        RubricStep.LOCATE_FLAW,
        stop_reason=StopReason.BUDGET_EXHAUSTED,
        step_source=StepSource.CHECKPOINTS,
        human_minutes=45.0,
    )
    assert Attempt.from_dict(a.to_dict()) == a


def test_old_log_records_load_with_defaults():
    a = Attempt.from_dict(
        {
            "challenge_id": "c",
            "level": "ASM_READING",
            "model": "m",
            "run_index": 0,
            "solved": False,
            "furthest_step": "NONE",
        }
    )
    assert a.stop_reason is StopReason.ANSWERED
    assert a.step_source is StepSource.CLAIMED
    assert a.human_minutes is None
    assert a.counted


def test_solved_must_be_answered():
    with pytest.raises(ValueError, match="ANSWERED"):
        Attempt(
            "c", "ASM_READING", "m", 0, True, RubricStep.DELIVER, stop_reason=StopReason.REFUSED
        )


def test_infra_error_is_not_counted():
    a = Attempt(
        "c", "ASM_READING", "m", 0, False, RubricStep.NONE, stop_reason=StopReason.INFRA_ERROR
    )
    assert not a.counted


@pytest.mark.parametrize(("field", "value"), [("stop_reason", "CRASHED"), ("step_source", "x")])
def test_from_dict_unknown_enum(field, value):
    data = {
        "challenge_id": "c",
        "level": "ASM_READING",
        "model": "m",
        "run_index": 0,
        "solved": False,
        "furthest_step": "NONE",
        field: value,
    }
    with pytest.raises(ValueError, match="unknown"):
        Attempt.from_dict(data)


def test_human_minutes_must_be_positive():
    with pytest.raises(ValueError, match="human_minutes"):
        Attempt("c", "ASM_READING", "m", 0, False, RubricStep.NONE, human_minutes=0)
