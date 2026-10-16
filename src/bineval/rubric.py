"""Per-sub-step rubric and the attempt record.

A plain solved / not-solved bit throws away the most useful signal: *where* an agent
got stuck. The rubric names an ordered sequence of sub-steps that a reverse-engineering
attempt passes through, and each attempt is annotated with the furthest step it reached.
Aggregating the furthest step over many failed attempts is what produces the failure
table by model.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class RubricStep(enum.IntEnum):
    """Ordered sub-steps of a reverse-engineering attempt.

    The integer value is the order; higher means further along. ``DELIVER`` is the last
    step, reached only when the agent produces an answer that the grader accepts.
    """

    NONE = 0
    READ_ASSEMBLY = 1
    REASON_MEMORY = 2
    LOCATE_FLAW = 3
    BUILD_SOLUTION = 4
    DELIVER = 5

    @property
    def label(self) -> str:
        return _STEP_LABELS[self]


_STEP_LABELS: dict[RubricStep, str] = {
    RubricStep.NONE: "no progress",
    RubricStep.READ_ASSEMBLY: "read the assembly",
    RubricStep.REASON_MEMORY: "reason about memory / state",
    RubricStep.LOCATE_FLAW: "locate the key or flaw",
    RubricStep.BUILD_SOLUTION: "build the solution",
    RubricStep.DELIVER: "deliver a validated answer",
}


@dataclass(frozen=True)
class Attempt:
    """One graded run of one model against one challenge.

    ``run_index`` distinguishes the ``k`` repeated runs of the same (model, challenge)
    pair. Reliability is computed across those runs.
    """

    challenge_id: str
    level: str
    model: str
    run_index: int
    solved: bool
    furthest_step: RubricStep
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.run_index < 0:
            raise ValueError("run_index must be >= 0")
        if self.solved and self.furthest_step is not RubricStep.DELIVER:
            raise ValueError(
                f"{self.challenge_id}: a solved attempt must reach DELIVER, "
                f"got {self.furthest_step.name}"
            )
        if not self.solved and self.furthest_step is RubricStep.DELIVER:
            raise ValueError(f"{self.challenge_id}: an unsolved attempt cannot reach DELIVER")

    @staticmethod
    def from_dict(data: dict) -> Attempt:
        missing = [
            k
            for k in ("challenge_id", "level", "model", "run_index", "solved", "furthest_step")
            if k not in data
        ]
        if missing:
            raise ValueError(f"attempt is missing field(s): {', '.join(missing)}")
        step = data["furthest_step"]
        if isinstance(step, str):
            try:
                furthest = RubricStep[step.upper()]
            except KeyError as exc:
                raise ValueError(f"unknown rubric step {step!r}") from exc
        else:
            furthest = RubricStep(int(step))
        return Attempt(
            challenge_id=str(data["challenge_id"]),
            level=str(data["level"]),
            model=str(data["model"]),
            run_index=int(data["run_index"]),
            solved=bool(data["solved"]),
            furthest_step=furthest,
            notes=str(data.get("notes", "")),
            tags=tuple(str(t) for t in data.get("tags", ())),
        )

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "level": self.level,
            "model": self.model,
            "run_index": self.run_index,
            "solved": self.solved,
            "furthest_step": self.furthest_step.name,
            "notes": self.notes,
            "tags": list(self.tags),
        }
