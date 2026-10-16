from __future__ import annotations

import hashlib

import pytest

from bineval.challenge import GraderKind, GraderSpec, load_challenge
from bineval.grader import grade


def _spec(kind: GraderKind, value: str, *, case_sensitive: bool = True) -> GraderSpec:
    return GraderSpec(kind=kind, value=value, case_sensitive=case_sensitive)


@pytest.mark.parametrize(
    ("submission", "expected"),
    [("flag{a}", True), ("  flag{a}\n", True), ("FLAG{A}", False), ("flag{b}", False)],
)
def test_exact_case_sensitive(submission, expected):
    assert grade(_spec(GraderKind.EXACT, "flag{a}"), submission).correct is expected


def test_exact_case_insensitive():
    assert grade(_spec(GraderKind.EXACT, "flag{a}", case_sensitive=False), "FLAG{A}").correct


def test_regex_requires_full_match():
    spec = _spec(GraderKind.REGEX, r"0x[0-9a-f]{4}")
    assert grade(spec, "0x1a2b").correct
    assert not grade(spec, "answer: 0x1a2b").correct
    assert not grade(spec, "0x1a2b3").correct


def test_regex_case_insensitive():
    spec = _spec(GraderKind.REGEX, r"0x[0-9a-f]{4}", case_sensitive=False)
    assert grade(spec, "0X1A2B").correct


def test_sha256_matches_digest_only():
    digest = hashlib.sha256(b"secret").hexdigest()
    spec = _spec(GraderKind.SHA256, digest)
    assert grade(spec, "secret").correct
    assert grade(spec, " secret \n").correct
    assert not grade(spec, "Secret").correct


def test_sha256_case_insensitive_and_uppercase_digest():
    digest = hashlib.sha256(b"secret").hexdigest().upper()
    spec = _spec(GraderKind.SHA256, digest, case_sensitive=False)
    assert grade(spec, "SECRET").correct


def test_outcome_has_reason():
    out = grade(_spec(GraderKind.EXACT, "a"), "b")
    assert not out.correct
    assert out.reason


def test_example_challenge_grades(example_challenge_path):
    ch = load_challenge(example_challenge_path)
    assert grade(ch.grader, "popcount").correct
    assert grade(ch.grader, "PopCount").correct
    assert not grade(ch.grader, "hamming").correct
