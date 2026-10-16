from __future__ import annotations

import pytest
from conftest import make_attempt

from bineval.metrics import FailureBreakdown, aggregate, level_sort_key, time_bucket
from bineval.rubric import RubricStep, StepSource, StopReason


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
    fb = FailureBreakdown("m", "L", {RubricStep.READ_ASSEMBLY: 2, RubricStep.BUILD_SOLUTION: 2})
    assert fb.modal_step is RubricStep.BUILD_SOLUTION


def test_modal_step_none_without_failures():
    assert FailureBreakdown("m", "L", {}).modal_step is None


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


def test_infra_errors_are_excluded_and_counted():
    attempts = [
        make_attempt("c1", run=0, stop=StopReason.INFRA_ERROR),
        make_attempt("c1", run=0, solved=True),  # the retry of run 0
        make_attempt("c1", run=1, stop=StopReason.INFRA_ERROR),  # never retried
        make_attempt("c2", run=0),
    ]
    agg = aggregate(attempts)
    assert agg.total_attempts == 4
    assert agg.infra_errors == 2
    assert agg.counted_attempts == 2
    assert agg.unresolved_runs == ("m/c1 run 1",)
    (summary,) = agg.level_summaries
    assert summary.n_attempts == 2
    assert summary.solve_rate == 0.5
    # A retried run is not a duplicate.
    assert not any("duplicate" in w for w in agg.warnings)


def test_solve_rate_weighs_challenges_equally():
    attempts = [
        make_attempt("c1", run=0, solved=True),
        make_attempt("c2", run=0),
        make_attempt("c2", run=1),
        make_attempt("c2", run=2),
    ]
    agg = aggregate(attempts)
    (summary,) = agg.level_summaries
    assert summary.solve_rate == 0.5  # not 1/4
    assert any("between 1 and 3 valid runs" in w for w in agg.warnings)


def test_consistency_counts_challenges_solved_every_run():
    attempts = [
        make_attempt("c1", run=0, solved=True),
        make_attempt("c1", run=1, solved=True),
        make_attempt("c2", run=0, solved=True),
        make_attempt("c2", run=1),
    ]
    (summary,) = aggregate(attempts).level_summaries
    assert summary.challenges_solved_any == 2
    assert summary.challenges_solved_all == 1
    assert summary.consistency == 0.5


def test_stop_counts_and_refusal_rate():
    attempts = [
        make_attempt("c1", run=0, stop=StopReason.REFUSED, step=RubricStep.NONE),
        make_attempt("c1", run=1, stop=StopReason.BUDGET_EXHAUSTED),
        make_attempt("c1", run=2, solved=True),
        make_attempt("c1", run=3, stop=StopReason.REFUSED, step=RubricStep.NONE),
    ]
    (summary,) = aggregate(attempts).level_summaries
    assert summary.stop_counts == {
        StopReason.REFUSED: 2,
        StopReason.BUDGET_EXHAUSTED: 1,
        StopReason.ANSWERED: 1,
    }
    assert summary.refusal_rate == 0.5


def test_failure_breakdown_is_split_by_level():
    attempts = [
        make_attempt("a", level="ASM_READING", step=RubricStep.NONE),
        make_attempt("v", level="VULN_DETECTION", step=RubricStep.BUILD_SOLUTION),
    ]
    fbs = aggregate(attempts).failure_breakdowns
    assert [(fb.level, fb.counts) for fb in fbs] == [
        ("ASM_READING", {RubricStep.NONE: 1}),
        ("VULN_DETECTION", {RubricStep.BUILD_SOLUTION: 1}),
    ]


def test_paired_comparison_uses_shared_challenges_only():
    attempts = [
        make_attempt("c1", model="a", solved=True),
        make_attempt("c2", model="a", solved=True),
        make_attempt("c3", model="a", solved=True),  # model b never ran c3
        make_attempt("c1", model="b"),
        make_attempt("c2", model="b", solved=True),
    ]
    (cmp,) = aggregate(attempts).comparisons
    assert (cmp.level, cmp.model_a, cmp.model_b) == ("ASM_READING", "a", "b")
    assert cmp.result.n_challenges == 2
    assert cmp.result.diff == 0.5


def test_no_comparison_for_a_single_model():
    assert aggregate([make_attempt("c1")]).comparisons == ()


@pytest.mark.parametrize(
    ("minutes", "bucket"),
    [(1, "< 15 min"), (15, "15-60 min"), (59.9, "15-60 min"), (60, "1-4 h"), (240, ">= 4 h")],
)
def test_time_bucket_boundaries(minutes, bucket):
    assert time_bucket(minutes) == bucket


def test_time_buckets_group_challenges_by_human_minutes():
    attempts = [
        make_attempt("quick", solved=True, minutes=5),
        make_attempt("slow", minutes=300),
        make_attempt("unknown", solved=True),
    ]
    agg = aggregate(attempts)
    assert [(t.bucket, t.n_challenges, t.estimate.rate) for t in agg.time_buckets] == [
        ("< 15 min", 1, 1.0),
        (">= 4 h", 1, 0.0),
    ]
    by_id = {r.challenge_id: r.human_minutes for r in agg.challenge_results}
    assert by_id == {"quick": 5, "slow": 300, "unknown": None}


def test_warns_on_inconsistent_human_minutes():
    attempts = [make_attempt("c1", run=0, minutes=5), make_attempt("c1", run=1, minutes=10)]
    assert any("human_minutes" in w for w in aggregate(attempts).warnings)


def test_step_sources_are_counted():
    attempts = [
        make_attempt("c1", run=0, source=StepSource.CHECKPOINTS),
        make_attempt("c1", run=1),
        make_attempt("c1", run=2, stop=StopReason.INFRA_ERROR),
    ]
    assert aggregate(attempts).step_sources == {
        StepSource.CHECKPOINTS: 1,
        StepSource.CLAIMED: 1,
    }
