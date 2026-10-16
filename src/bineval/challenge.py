"""Challenge schema and loading.

A challenge is metadata plus a self-validating grader. It deliberately does *not*
reference a concrete binary in the public repository: binaries live outside version
control (see ``.gitignore``) and are built locally in an isolated lab. A challenge only
needs to know how to recognise a correct answer, which is what the grader spec records.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path

import yaml


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
        return GraderSpec(
            kind=kind,
            value=str(data["value"]),
            case_sensitive=bool(data.get("case_sensitive", True)),
        )


@dataclass(frozen=True)
class Challenge:
    """One gradable task."""

    id: str
    level: Level
    title: str
    grader: GraderSpec
    description: str = ""
    difficulty: int = 1
    source: str = "own"
    tags: tuple[str, ...] = field(default_factory=tuple)
    points: int = 1

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("challenge 'id' must be non-empty")
        if not 1 <= self.difficulty <= 10:
            raise ValueError(
                f"challenge {self.id!r}: difficulty must be 1..10, got {self.difficulty}"
            )
        if self.points < 0:
            raise ValueError(f"challenge {self.id!r}: points must be >= 0")

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
        tags = tuple(str(t) for t in data.get("tags", ()))
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
        )


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
