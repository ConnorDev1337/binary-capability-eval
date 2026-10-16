"""Challenge schema and loading.

A challenge is metadata plus a self-validating grader. It deliberately does *not*
reference a concrete binary in the public repository: binaries live outside version
control (see ``.gitignore``) and are built locally in an isolated lab. A challenge only
needs to know how to recognise a correct answer, which is what the grader spec records.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bineval.rubric import RubricStep

_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}")

# Bump when the canonical form hashed by challenge_set_hash() changes.
_SET_HASH_SCHEME = 1


class Level(enum.StrEnum):
    """Difficulty tiers, ordered from least to most dangerous."""

    ASM_READING = "ASM_READING"
    SIMPLE_REVERSING = "SIMPLE_REVERSING"
    VULN_DETECTION = "VULN_DETECTION"
    FULL_EXPLOITATION = "FULL_EXPLOITATION"

    @property
    def rank(self) -> int:
        return _LEVEL_ORDER.index(self)


_LEVEL_ORDER: list[Level] = [
    Level.ASM_READING,
    Level.SIMPLE_REVERSING,
    Level.VULN_DETECTION,
    Level.FULL_EXPLOITATION,
]


class GraderKind(enum.StrEnum):
    """How a submitted answer is checked against the expected one."""

    EXACT = "exact"
    REGEX = "regex"
    SHA256 = "sha256"


@dataclass(frozen=True)
class GraderSpec:
    """How to recognise a correct answer.

    For ``SHA256`` the expected answer is stored only as a digest, so the repository
    never contains the plaintext flag. ``EXACT`` and ``REGEX`` store the comparison
    value directly, which is fine for public challenges whose answer is not a secret.
    """

    kind: GraderKind
    value: str
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        # A malformed spec can never accept any answer, which would silently record every
        # attempt as a failure. Reject it at load time instead.
        if self.kind is GraderKind.SHA256 and not _SHA256_HEX.fullmatch(self.value.strip()):
            raise ValueError("sha256 grader 'value' must be a 64-character hex digest")
        if self.kind is GraderKind.REGEX:
            try:
                re.compile(self.value)
            except re.error as exc:
                raise ValueError(f"regex grader 'value' does not compile: {exc}") from exc

    @staticmethod
    def from_dict(data: dict) -> GraderSpec:
        try:
            kind = GraderKind(str(data["kind"]).lower())
        except KeyError as exc:
            raise ValueError("grader is missing 'kind'") from exc
        except ValueError as exc:
            raise ValueError(
                f"unknown grader kind {data.get('kind')!r}; "
                f"expected one of {[k.value for k in GraderKind]}"
            ) from exc
        if "value" not in data:
            raise ValueError("grader is missing 'value'")
        case_sensitive = data.get("case_sensitive", True)
        if not isinstance(case_sensitive, bool):
            # bool("false") is True, so a quoted YAML value would silently flip the meaning.
            raise ValueError(
                f"grader 'case_sensitive' must be true or false, got {case_sensitive!r}"
            )
        return GraderSpec(kind=kind, value=str(data["value"]), case_sensitive=case_sensitive)

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "value": self.value, "case_sensitive": self.case_sensitive}


@dataclass(frozen=True)
class Checkpoint:
    """A graded intermediate result that evidences one rubric step.

    A checkpoint turns a step label from a judgement into a measurement: if the agent can
    state, say, the size of the buffer the flaw hinges on, it reached ``LOCATE_FLAW``.
    When a challenge defines checkpoints, the recorded step comes only from the ones that
    pass, and the runner's own claim is ignored.
    """

    id: str
    step: RubricStep
    question: str
    grader: GraderSpec

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("checkpoint 'id' must be non-empty")
        if self.step in (RubricStep.NONE, RubricStep.DELIVER):
            # DELIVER belongs to the challenge's own grader; NONE is not evidence of anything.
            raise ValueError(f"checkpoint {self.id!r}: step cannot be {self.step.name}")

    @staticmethod
    def from_dict(data: dict) -> Checkpoint:
        missing = [k for k in ("id", "step", "question", "grader") if k not in data]
        if missing:
            raise ValueError(f"checkpoint is missing field(s): {', '.join(missing)}")
        try:
            step = RubricStep[str(data["step"]).upper()]
        except KeyError as exc:
            raise ValueError(f"checkpoint has unknown step {data['step']!r}") from exc
        return Checkpoint(
            id=str(data["id"]),
            step=step,
            question=str(data["question"]),
            grader=GraderSpec.from_dict(dict(data["grader"])),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "step": self.step.name,
            "question": self.question,
            "grader": self.grader.to_dict(),
        }


@dataclass(frozen=True)
class Challenge:
    """One gradable task.

    ``human_minutes`` is an optional estimate of how long a competent human reverse
    engineer needs, which lets results be read against task length and not only level.
    """

    id: str
    level: Level
    title: str
    grader: GraderSpec
    description: str = ""
    difficulty: int = 1
    source: str = "own"
    tags: tuple[str, ...] = field(default_factory=tuple)
    points: int = 1
    human_minutes: float | None = None
    checkpoints: tuple[Checkpoint, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("challenge 'id' must be non-empty")
        if not 1 <= self.difficulty <= 10:
            raise ValueError(
                f"challenge {self.id!r}: difficulty must be 1..10, got {self.difficulty}"
            )
        if self.points < 0:
            raise ValueError(f"challenge {self.id!r}: points must be >= 0")
        if self.human_minutes is not None and self.human_minutes <= 0:
            raise ValueError(f"challenge {self.id!r}: human_minutes must be > 0")
        ids = [cp.id for cp in self.checkpoints]
        if len(set(ids)) != len(ids):
            raise ValueError(f"challenge {self.id!r}: duplicate checkpoint ids {sorted(ids)}")

    @staticmethod
    def from_dict(data: dict) -> Challenge:
        missing = [k for k in ("id", "level", "title", "grader") if k not in data]
        if missing:
            raise ValueError(f"challenge is missing required field(s): {', '.join(missing)}")
        try:
            level = Level(str(data["level"]).upper())
        except ValueError as exc:
            raise ValueError(
                f"unknown level {data['level']!r}; expected one of {[x.value for x in Level]}"
            ) from exc
        raw_tags = data.get("tags", ())
        if isinstance(raw_tags, str):
            # A bare string would otherwise be split into one tag per character.
            raise ValueError(f"'tags' must be a list, got the string {raw_tags!r}")
        tags = tuple(str(t) for t in raw_tags)
        raw_checkpoints = data.get("checkpoints", ())
        if not isinstance(raw_checkpoints, list | tuple):
            raise ValueError("'checkpoints' must be a list")
        checkpoints = []
        for i, raw in enumerate(raw_checkpoints):
            try:
                checkpoints.append(Checkpoint.from_dict(dict(raw)))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"checkpoint {i}: {exc}") from exc
        human_minutes = data.get("human_minutes")
        return Challenge(
            id=str(data["id"]),
            level=level,
            title=str(data["title"]),
            grader=GraderSpec.from_dict(dict(data["grader"])),
            description=str(data.get("description", "")),
            difficulty=int(data.get("difficulty", 1)),
            source=str(data.get("source", "own")),
            tags=tags,
            points=int(data.get("points", 1)),
            human_minutes=None if human_minutes is None else float(human_minutes),
            checkpoints=tuple(checkpoints),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "source": self.source,
            "tags": list(self.tags),
            "points": self.points,
            "human_minutes": self.human_minutes,
            "grader": self.grader.to_dict(),
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
        }


def challenge_set_hash(challenges: Iterable[Challenge]) -> str:
    """SHA-256 over the parsed content of a challenge set, independent of file layout.

    The hash covers every field, in id order, so editing a description or a grader changes
    it, while reformatting YAML, adding comments, or moving files does not. Publish it with
    results so a private set can later be shown to be the one that was evaluated.
    """

    payload = {
        "scheme": _SET_HASH_SCHEME,
        "challenges": [c.to_dict() for c in sorted(challenges, key=lambda c: c.id)],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_challenge(path: str | Path) -> Challenge:
    """Load and validate a single challenge from a YAML file."""

    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected a YAML mapping at the top level")
    try:
        return Challenge.from_dict(data)
    except ValueError as exc:
        raise ValueError(f"{p}: {exc}") from exc


def load_challenges(directory: str | Path) -> list[Challenge]:
    """Load every ``*.yaml`` / ``*.yml`` challenge under *directory*, sorted by id.

    Raises ``ValueError`` if two challenges share an id, since metrics key on it.
    """

    root = Path(directory)
    files = sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")])
    challenges: list[Challenge] = []
    seen: dict[str, Path] = {}
    for f in files:
        ch = load_challenge(f)
        if ch.id in seen:
            raise ValueError(f"duplicate challenge id {ch.id!r} in {f} and {seen[ch.id]}")
        seen[ch.id] = f
        challenges.append(ch)
    challenges.sort(key=lambda c: c.id)
    return challenges
