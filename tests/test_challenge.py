from __future__ import annotations

import pytest

from bineval.challenge import (
    Challenge,
    GraderKind,
    GraderSpec,
    Level,
    challenge_set_hash,
    load_challenge,
    load_challenges,
)
from bineval.rubric import RubricStep


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


def test_sha256_value_must_be_a_digest():
    with pytest.raises(ValueError, match="64-character hex digest"):
        GraderSpec(GraderKind.SHA256, "not-a-digest")
    GraderSpec(GraderKind.SHA256, "AB" * 32)  # upper-case hex is accepted


def test_regex_value_must_compile():
    with pytest.raises(ValueError, match="does not compile"):
        GraderSpec(GraderKind.REGEX, "flag{[")


def test_case_sensitive_must_be_bool():
    data = _valid() | {"grader": {"kind": "exact", "value": "v", "case_sensitive": "false"}}
    with pytest.raises(ValueError, match="case_sensitive"):
        Challenge.from_dict(data)


def test_tags_string_rejected():
    with pytest.raises(ValueError, match="tags"):
        Challenge.from_dict(_valid() | {"tags": "x86-64"})


def test_set_hash_ignores_order():
    a = Challenge.from_dict(_valid())
    b = Challenge.from_dict(_valid() | {"id": "x-002"})
    assert challenge_set_hash([a, b]) == challenge_set_hash([b, a])
    assert len(challenge_set_hash([a])) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"description": "edited"},
        {"grader": {"kind": "exact", "value": "43"}},
        {"grader": {"kind": "exact", "value": "42", "case_sensitive": False}},
        {"level": "SIMPLE_REVERSING"},
    ],
)
def test_set_hash_changes_with_content(change):
    base = challenge_set_hash([Challenge.from_dict(_valid())])
    assert challenge_set_hash([Challenge.from_dict(_valid() | change)]) != base


def test_set_hash_independent_of_yaml_layout(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "one.yaml").write_text(
        "id: c\nlevel: ASM_READING\ntitle: t\ngrader: {kind: exact, value: v}\n",
        encoding="utf-8",
    )
    (tmp_path / "b" / "renamed.yml").write_text(
        "# a comment\nid: c\ntitle: t\nlevel: asm_reading\ngrader:\n  kind: EXACT\n  value: v\n",
        encoding="utf-8",
    )
    assert challenge_set_hash(load_challenges(tmp_path / "a")) == challenge_set_hash(
        load_challenges(tmp_path / "b")
    )


def _checkpoint(cid: str = "cp1", step: str = "LOCATE_FLAW") -> dict:
    return {"id": cid, "step": step, "question": "q?", "grader": {"kind": "exact", "value": "8"}}


def test_checkpoints_and_human_minutes_parse():
    ch = Challenge.from_dict(_valid() | {"human_minutes": 30, "checkpoints": [_checkpoint()]})
    assert ch.human_minutes == 30.0
    (cp,) = ch.checkpoints
    assert cp.step is RubricStep.LOCATE_FLAW
    assert cp.grader.kind is GraderKind.EXACT


@pytest.mark.parametrize("step", ["NONE", "DELIVER"])
def test_checkpoint_step_cannot_be_none_or_deliver(step):
    with pytest.raises(ValueError, match=f"checkpoint 0: .*{step}"):
        Challenge.from_dict(_valid() | {"checkpoints": [_checkpoint(step=step)]})


@pytest.mark.parametrize(
    ("checkpoints", "match"),
    [
        ([_checkpoint(step="GUESS")], "unknown step"),
        ([{"id": "x"}], "missing"),
        ([_checkpoint(), _checkpoint()], "duplicate checkpoint"),
        ("cp1", "must be a list"),
    ],
)
def test_bad_checkpoints(checkpoints, match):
    with pytest.raises(ValueError, match=match):
        Challenge.from_dict(_valid() | {"checkpoints": checkpoints})


def test_human_minutes_must_be_positive():
    with pytest.raises(ValueError, match="human_minutes"):
        Challenge.from_dict(_valid() | {"human_minutes": 0})


def test_set_hash_covers_checkpoints_and_human_minutes():
    base = challenge_set_hash([Challenge.from_dict(_valid())])
    for change in ({"human_minutes": 5}, {"checkpoints": [_checkpoint()]}):
        assert challenge_set_hash([Challenge.from_dict(_valid() | change)]) != base


def test_example_defines_a_checkpoint(example_challenge_path):
    ch = load_challenge(example_challenge_path)
    assert ch.human_minutes is not None
    assert [cp.step for cp in ch.checkpoints] == [RubricStep.REASON_MEMORY]
