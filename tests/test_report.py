from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, make_attempt

from bineval.metrics import aggregate
from bineval.report import (
    append_attempt,
    json_summary,
    load_attempts,
    markdown_report,
    write_attempts,
)
from bineval.rubric import RubricStep, StepSource, StopReason


def test_jsonl_round_trip(tmp_path):
    attempts = [
        make_attempt("c1", solved=True),
        make_attempt("c2", step=RubricStep.LOCATE_FLAW),
    ]
    path = tmp_path / "a.jsonl"
    write_attempts(path, attempts)
    assert load_attempts(path) == attempts


def test_load_skips_blank_lines(tmp_path):
    path = tmp_path / "a.jsonl"
    write_attempts(path, [make_attempt("c1")])
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    assert len(load_attempts(path)) == 1


def test_load_reports_line_number(tmp_path):
    path = tmp_path / "a.jsonl"
    write_attempts(path, [make_attempt("c1")])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{not json}\n")
    with pytest.raises(ValueError, match=r"a\.jsonl:2"):
        load_attempts(path)


def test_markdown_empty():
    assert "No attempts" in markdown_report(aggregate([]))


def test_markdown_has_all_sections():
    agg = aggregate(
        [
            make_attempt("c1", solved=True),
            make_attempt("c1", run=1, step=RubricStep.BUILD_SOLUTION),
        ]
    )
    md = markdown_report(agg, title="T")
    assert md.startswith("# T\n")
    for heading in (
        "## Capability by level",
        "## Where unsolved attempts stopped",
        "## Reliability per challenge",
    ):
        assert heading in md
    assert "50.0%" in md
    assert "build the solution" in md
    assert "Data warnings" not in md


def test_markdown_all_solved():
    md = markdown_report(aggregate([make_attempt("c1", solved=True)]))
    assert "No unsolved attempts" in md


def test_markdown_lists_warnings():
    agg = aggregate([make_attempt("c1"), make_attempt("c1")])
    assert "## Data warnings" in markdown_report(agg)


def test_json_summary_is_serialisable():
    agg = aggregate([make_attempt("c1", solved=True), make_attempt("c2")])
    data = json.loads(json.dumps(json_summary(agg)))
    assert data["total_attempts"] == 2
    assert data["failure_breakdowns"][0]["counts"] == {"READ_ASSEMBLY": 1}
    assert data["failure_breakdowns"][0]["modal_step"] == "READ_ASSEMBLY"


def test_synthetic_example_loads_and_is_labelled():
    attempts = load_attempts(EXAMPLES / "attempts.synthetic.jsonl")
    assert attempts
    assert all(a.model.startswith("synthetic-") for a in attempts)
    assert all("synthetic" in a.notes for a in attempts)
    agg = aggregate(attempts)
    assert not agg.warnings


def test_append_attempt_creates_log_and_round_trips(tmp_path):
    log = tmp_path / "runs" / "m.jsonl"
    first = make_attempt("c1", stop=StopReason.REFUSED, step=RubricStep.NONE, minutes=7)
    second = make_attempt("c1", run=1, source=StepSource.CHECKPOINTS)
    append_attempt(log, first)
    append_attempt(log, second)
    assert load_attempts(log) == [first, second]


def test_markdown_new_sections():
    agg = aggregate(
        [
            make_attempt("c1", model="a", solved=True, minutes=5),
            make_attempt("c2", model="a", stop=StopReason.REFUSED, step=RubricStep.NONE),
            make_attempt("c1", model="b", minutes=5),
            make_attempt("c2", model="b", stop=StopReason.INFRA_ERROR),
        ]
    )
    md = markdown_report(agg)
    for heading in (
        "## How attempts ended",
        "## Paired comparison",
        "## Solve rate by estimated human solve time",
        "## Excluded attempts",
    ):
        assert heading in md
    assert "Refusals count as unsolved" in md
    assert "- b/c2 run 0" in md
    assert "95% CI" in md
    assert "human min" in md


def test_markdown_omits_optional_sections_when_unused():
    md = markdown_report(aggregate([make_attempt("c1", solved=True)]))
    for heading in ("Paired comparison", "human solve time", "Excluded attempts", "Refusals"):
        assert heading not in md


def test_markdown_caps_unresolved_list():
    agg = aggregate(
        [make_attempt(f"c{i}", stop=StopReason.INFRA_ERROR) for i in range(25)]
        + [make_attempt("ok")]
    )
    md = markdown_report(agg)
    assert "25 run(s) still have no valid result" in md
    assert "... and 5 more" in md


def test_markdown_resolved_errors():
    agg = aggregate(
        [make_attempt("c1", stop=StopReason.INFRA_ERROR), make_attempt("c1", solved=True)]
    )
    assert "Every one of those runs was re-run" in markdown_report(agg)


def test_json_summary_has_uncertainty_and_comparisons():
    agg = aggregate(
        [
            make_attempt("c1", model="a", solved=True),
            make_attempt("c2", model="a"),
            make_attempt("c1", model="b"),
            make_attempt("c2", model="b"),
        ]
    )
    data = json.loads(json.dumps(json_summary(agg)))
    est = data["level_summaries"][0]["solve_rate_estimate"]
    assert set(est) == {"rate", "se", "n_eff", "ci_low", "ci_high"}
    assert data["comparisons"][0]["diff"] == 0.5
    assert data["failure_breakdowns"][0]["level"] == "ASM_READING"
    assert data["bineval_version"]
