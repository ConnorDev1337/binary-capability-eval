from __future__ import annotations

import pytest

from bineval.rubric import Attempt, RubricStep


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
