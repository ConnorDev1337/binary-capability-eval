from __future__ import annotations

import pytest
from conftest import make_attempt

from bineval.metrics import FailureBreakdown, aggregate, level_sort_key
from bineval.rubric import RubricStep


def test_empty():
    agg = aggregate([])
    assert agg.total_attempts == 0
    assert agg.level_summaries == ()


def test_reliability_and_solve_rate():
    attempts = [
        make_attempt("c1", run=0, solved=True),
        make_attempt("c1", run=1, solved=False),
        make_attempt("c1", run=2, solved=True),
        make_attempt("c2", run=0, solved=False),
        make_attempt("c2", run=1, solved=False),
        make_attempt("c2", run=2, solved=False),
    ]
    agg = aggregate(attempts)

    by_id = {r.challenge_id: r for r in agg.challenge_results}
    assert by_id["c1"].reliability == pytest.approx(2 / 3)
    assert by_id["c2"].reliability == 0.0
    assert by_id["c1"].solved_any and not by_id["c2"].solved_any

    (summary,) = agg.level_summaries
    assert summary.n_challenges == 2
    assert summary.n_attempts == 6
    assert summary.solve_rate == pytest.approx(2 / 6)
    assert summary.coverage == pytest.approx(1 / 2)


def test_levels_ordered_by_difficulty_not_alphabet():
    attempts = [
        make_attempt("v", level="VULN_DETECTION"),
        make_attempt("f", level="FULL_EXPLOITATION"),
        make_attempt("a", level="ASM_READING"),
        make_attempt("s", level="SIMPLE_REVERSING"),
    ]
    agg = aggregate(attempts)
    assert agg.levels == (
        "ASM_READING",
        "SIMPLE_REVERSING",
        "VULN_DETECTION",
        "FULL_EXPLOITATION",
    )
    assert [s.level for s in agg.level_summaries] == list(agg.levels)


def test_unknown_level_sorts_last():
    assert level_sort_key("CUSTOM") > level_sort_key("FULL_EXPLOITATION")


def test_failure_breakdown_counts_only_unsolved():
    attempts = [
        make_attempt("c1", run=0, solved=True),
        make_attempt("c1", run=1, step=RubricStep.LOCATE_FLAW),
        make_attempt("c1", run=2, step=RubricStep.LOCATE_FLAW),
        make_attempt("c2", run=0, step=RubricStep.READ_ASSEMBLY),
    ]
    (fb,) = aggregate(attempts).failure_breakdowns
    assert fb.total == 3
    assert fb.counts == {RubricStep.LOCATE_FLAW: 2, RubricStep.READ_ASSEMBLY: 1}
    assert fb.modal_step is RubricStep.LOCATE_FLAW


def test_modal_step_tie_prefers_further_step():
    fb = FailureBreakdown("m", {RubricStep.READ_ASSEMBLY: 2, RubricStep.BUILD_SOLUTION: 2})
    assert fb.modal_step is RubricStep.BUILD_SOLUTION


def test_modal_step_none_without_failures():
    assert FailureBreakdown("m", {}).modal_step is None


def test_models_separated():
    attempts = [
        make_attempt("c1", model="a", solved=True),
        make_attempt("c1", model="b", solved=False),
    ]
    agg = aggregate(attempts)
    assert agg.models == ("a", "b")
    rates = {s.model: s.solve_rate for s in agg.level_summaries}
    assert rates == {"a": 1.0, "b": 0.0}


def test_warns_on_duplicate_run_index():
    attempts = [make_attempt("c1", run=0), make_attempt("c1", run=0)]
    assert any("duplicate run_index" in w for w in aggregate(attempts).warnings)


def test_warns_on_inconsistent_level():
    attempts = [
        make_attempt("c1", level="ASM_READING", run=0),
        make_attempt("c1", level="VULN_DETECTION", run=1),
    ]
    assert any("levels" in w for w in aggregate(attempts).warnings)
