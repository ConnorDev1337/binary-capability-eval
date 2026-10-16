from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES, make_attempt

from bineval.metrics import aggregate
from bineval.report import json_summary, load_attempts, markdown_report, write_attempts
from bineval.rubric import RubricStep


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
