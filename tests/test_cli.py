from __future__ import annotations

import hashlib
import io
import json

import pytest
from conftest import EXAMPLES, make_attempt

from bineval import __version__
from bineval.cli import main
from bineval.report import write_attempts


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_validate_file(capsys, example_challenge_path):
    assert main(["validate", str(example_challenge_path)]) == 0
    assert "1 challenge(s) valid" in capsys.readouterr().out


def test_validate_directory(capsys):
    assert main(["validate", str(EXAMPLES)]) == 0
    assert "asm-reading-001" in capsys.readouterr().out


def test_validate_bad_file(capsys, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == 1
    assert "error:" in capsys.readouterr().err


def test_grade_exit_codes(capsys, example_challenge_path):
    assert main(["grade", str(example_challenge_path), "popcount"]) == 0
    assert "CORRECT" in capsys.readouterr().out
    assert main(["grade", str(example_challenge_path), "nope"]) == 1
    assert "INCORRECT" in capsys.readouterr().out


def test_grade_stdin(monkeypatch, capsys, example_challenge_path):
    monkeypatch.setattr("sys.stdin", io.StringIO("popcount\n"))
    assert main(["grade", str(example_challenge_path), "-"]) == 0


def test_grade_missing_challenge(capsys, tmp_path):
    assert main(["grade", str(tmp_path / "missing.yaml"), "x"]) == 2


def test_hash(capsys):
    assert main(["hash", "  Answer "]) == 0
    assert capsys.readouterr().out.strip() == hashlib.sha256(b"Answer").hexdigest()
    assert main(["hash", "--case-insensitive", "Answer"]) == 0
    assert capsys.readouterr().out.strip() == hashlib.sha256(b"answer").hexdigest()


def test_report_markdown_stdout(capsys):
    assert main(["report", str(EXAMPLES / "attempts.synthetic.jsonl")]) == 0
    assert "## Capability by level" in capsys.readouterr().out


def test_report_json_to_file(tmp_path):
    out = tmp_path / "summary.json"
    log = str(EXAMPLES / "attempts.synthetic.jsonl")
    rc = main(["report", log, "--format", "json", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["models"] == ["synthetic-model-a", "synthetic-model-b"]


def _write_log(path, model: str, solved: dict[str, bool]) -> str:
    write_attempts(path, [make_attempt(c, model=model, solved=s) for c, s in solved.items()])
    return str(path)


def test_report_tagged_logs_compare_one_model(capsys, tmp_path):
    base = _write_log(tmp_path / "base.jsonl", "m", {"c1": False, "c2": False})
    tuned = _write_log(tmp_path / "tuned.jsonl", "m", {"c1": True, "c2": False})
    assert main(["report", base, tuned, "--tag", "base", "--tag", "tuned"]) == 0
    out = capsys.readouterr().out
    assert "## Paired comparison" in out
    assert "| ASM_READING | m [base] | m [tuned] | 2 | -50.0 pp |" in out


def test_report_untagged_logs_are_read_together(tmp_path):
    a = _write_log(tmp_path / "a.jsonl", "model-a", {"c1": True})
    b = _write_log(tmp_path / "b.jsonl", "model-b", {"c1": False})
    out = tmp_path / "summary.json"
    assert main(["report", a, b, "--format", "json", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["models"] == ["model-a", "model-b"]
    assert data["total_attempts"] == 2


def test_report_tag_count_must_match_logs(capsys, tmp_path):
    a = _write_log(tmp_path / "a.jsonl", "m", {"c1": True})
    b = _write_log(tmp_path / "b.jsonl", "m", {"c1": True})
    assert main(["report", a, b, "--tag", "only-one"]) == 2
    assert "1 --tag value(s) for 2 log(s)" in capsys.readouterr().err


def test_report_bad_log(capsys, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("nope\n", encoding="utf-8")
    assert main(["report", str(bad)]) == 1


def test_set_hash(capsys):
    assert main(["set-hash", str(EXAMPLES)]) == 0
    digest, count = capsys.readouterr().out.split(maxsplit=1)
    assert len(digest) == 64
    assert "1 challenge(s)" in count


def test_set_hash_empty_directory(capsys, tmp_path):
    assert main(["set-hash", str(tmp_path)]) == 1
    assert "no challenges" in capsys.readouterr().err
