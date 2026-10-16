from __future__ import annotations

import hashlib
import io
import json

import pytest
from conftest import EXAMPLES

from bineval import __version__
from bineval.cli import main


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
