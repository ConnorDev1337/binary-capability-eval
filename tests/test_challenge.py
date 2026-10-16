from __future__ import annotations

import pytest

from bineval.challenge import (
    Challenge,
    GraderKind,
    GraderSpec,
    Level,
    load_challenge,
    load_challenges,
)


def _valid() -> dict:
    return {
        "id": "x-001",
        "level": "asm_reading",
        "title": "t",
        "grader": {"kind": "EXACT", "value": "42"},
    }


def test_from_dict_minimal_defaults():
    ch = Challenge.from_dict(_valid())
    assert ch.level is Level.ASM_READING
    assert ch.grader.kind is GraderKind.EXACT
    assert ch.difficulty == 1
    assert ch.source == "own"
    assert ch.tags == ()


@pytest.mark.parametrize("field", ["id", "level", "title", "grader"])
def test_missing_required_field(field):
    data = _valid()
    del data[field]
    with pytest.raises(ValueError, match=field):
        Challenge.from_dict(data)


def test_unknown_level():
    data = _valid() | {"level": "EASY"}
    with pytest.raises(ValueError, match="unknown level"):
        Challenge.from_dict(data)


def test_unknown_grader_kind():
    data = _valid() | {"grader": {"kind": "fuzzy", "value": "x"}}
    with pytest.raises(ValueError, match="unknown grader kind"):
        Challenge.from_dict(data)


def test_grader_missing_value():
    with pytest.raises(ValueError, match="value"):
        GraderSpec.from_dict({"kind": "exact"})


@pytest.mark.parametrize("difficulty", [0, 11])
def test_difficulty_bounds(difficulty):
    with pytest.raises(ValueError, match="difficulty"):
        Challenge.from_dict(_valid() | {"difficulty": difficulty})


def test_level_rank_is_ordered():
    ranks = [lvl.rank for lvl in Level]
    assert ranks == sorted(ranks)
    assert Level.ASM_READING.rank < Level.FULL_EXPLOITATION.rank


def test_load_example(example_challenge_path):
    ch = load_challenge(example_challenge_path)
    assert ch.id == "asm-reading-001"
    assert ch.grader.kind is GraderKind.SHA256
    assert ch.grader.case_sensitive is False


def test_load_non_mapping(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_challenge(p)


def test_load_error_names_file(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("id: a\nlevel: ASM_READING\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.yaml"):
        load_challenge(p)


def test_load_challenges_sorted_and_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    for name, cid in [("b.yaml", "b"), ("sub/a.yml", "a")]:
        (tmp_path / name).write_text(
            f"id: {cid}\nlevel: ASM_READING\ntitle: t\ngrader: {{kind: exact, value: v}}\n",
            encoding="utf-8",
        )
    assert [c.id for c in load_challenges(tmp_path)] == ["a", "b"]


def test_load_challenges_duplicate_id(tmp_path):
    for name in ("one.yaml", "two.yaml"):
        (tmp_path / name).write_text(
            "id: same\nlevel: ASM_READING\ntitle: t\ngrader: {kind: exact, value: v}\n",
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="duplicate"):
        load_challenges(tmp_path)
