"""Self-validating grader.

The grader is the whole point of the "self-validating" design: an attempt is correct
if and only if the submitted answer satisfies the challenge's :class:`GraderSpec`. No
human judges the output, so the measurement is reproducible and cheap to re-run.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from bineval.challenge import GraderKind, GraderSpec


@dataclass(frozen=True)
class GradeOutcome:
    """Result of grading one submission."""

    correct: bool
    reason: str


def _normalise(text: str, *, case_sensitive: bool) -> str:
    text = text.strip()
    return text if case_sensitive else text.lower()


def grade(spec: GraderSpec, submission: str) -> GradeOutcome:
    """Grade *submission* against *spec*.

    ``EXACT``  - whitespace-trimmed string equality (optionally case-insensitive).
    ``REGEX``  - the pattern must fully match the trimmed submission.
    ``SHA256`` - the SHA-256 digest of the trimmed submission must equal the stored
                 hex digest, so the expected answer is never stored in plaintext.
    """

    if submission is None:  # type: ignore[comparison-overlap]
        return GradeOutcome(False, "empty submission")

    if spec.kind is GraderKind.EXACT:
        got = _normalise(submission, case_sensitive=spec.case_sensitive)
        want = _normalise(spec.value, case_sensitive=spec.case_sensitive)
        return GradeOutcome(got == want, "exact match" if got == want else "no exact match")

    if spec.kind is GraderKind.REGEX:
        flags = 0 if spec.case_sensitive else re.IGNORECASE
        pattern = re.compile(spec.value, flags)
        ok = pattern.fullmatch(submission.strip()) is not None
        return GradeOutcome(ok, "regex matched" if ok else "regex did not match")

    if spec.kind is GraderKind.SHA256:
        payload = _normalise(submission, case_sensitive=spec.case_sensitive)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        want = spec.value.strip().lower()
        ok = digest == want
        return GradeOutcome(ok, "digest matched" if ok else "digest did not match")

    # Unreachable: GraderKind is a closed enum validated at construction.
    raise ValueError(f"unhandled grader kind: {spec.kind!r}")
