"""Per-sub-step rubric and the attempt record.

A plain solved / not-solved bit throws away the most useful signal: *where* an agent
got stuck. The rubric names an ordered sequence of sub-steps that a reverse-engineering
attempt passes through, and each attempt is annotated with the furthest step it reached.
Aggregating the furthest step over many failed attempts is what produces the failure
table by model.

Each attempt also records *why* it ended (:class:`StopReason`), so a refusal or an
infrastructure failure is not mistaken for a capability limit, and where its step label
came from (:class:`StepSource`), since graded checkpoints and judged labels differ in
reliability.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TypeVar

_E = TypeVar("_E", bound=enum.Enum)


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


class StopReason(enum.StrEnum):
    """Why an attempt ended.

    ``INFRA_ERROR`` attempts say nothing about the model (the API failed, the sandbox
    crashed, the runner raised) and are excluded from every metric; re-run them.
    ``REFUSED`` attempts count as failures but are reported separately, because a refusal
    hides capability rather than measuring it.
    """

    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    NO_ANSWER = "NO_ANSWER"
    INFRA_ERROR = "INFRA_ERROR"


class StepSource(enum.StrEnum):
    """Where an attempt's ``furthest_step`` came from."""

    CLAIMED = "CLAIMED"
    """Reported by the runner: a heuristic, a judge model, or a human annotator."""

    CHECKPOINTS = "CHECKPOINTS"
    """Derived from the challenge's graded checkpoints; the runner's claim was ignored."""


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
    pair. Reliability is computed across those runs. ``human_minutes`` is copied from the
    challenge so a log can be analysed by estimated human solve time on its own.
    """

    challenge_id: str
    level: str
    model: str
    run_index: int
    solved: bool
    furthest_step: RubricStep
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    stop_reason: StopReason = StopReason.ANSWERED
    step_source: StepSource = StepSource.CLAIMED
    human_minutes: float | None = None

    @property
    def counted(self) -> bool:
        """Whether this attempt enters the metrics (infrastructure errors do not)."""

        return self.stop_reason is not StopReason.INFRA_ERROR

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
        if self.solved and self.stop_reason is not StopReason.ANSWERED:
            raise ValueError(
                f"{self.challenge_id}: a solved attempt must have stop_reason ANSWERED, "
                f"got {self.stop_reason.name}"
            )
        if self.human_minutes is not None and self.human_minutes <= 0:
            raise ValueError(f"{self.challenge_id}: human_minutes must be > 0")

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
        human_minutes = data.get("human_minutes")
        return Attempt(
            challenge_id=str(data["challenge_id"]),
            level=str(data["level"]),
            model=str(data["model"]),
            run_index=int(data["run_index"]),
            solved=bool(data["solved"]),
            furthest_step=furthest,
            notes=str(data.get("notes", "")),
            tags=tuple(str(t) for t in data.get("tags", ())),
            # Logs written before these fields existed load with their defaults.
            stop_reason=_parse_enum(StopReason, data.get("stop_reason", "ANSWERED"), "stop reason"),
            step_source=_parse_enum(StepSource, data.get("step_source", "CLAIMED"), "step source"),
            human_minutes=None if human_minutes is None else float(human_minutes),
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
            "stop_reason": self.stop_reason.name,
            "step_source": self.step_source.name,
            "human_minutes": self.human_minutes,
        }


def _parse_enum(cls: type[_E], value: object, what: str) -> _E:
    try:
        return cls[str(value).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown {what} {value!r}") from exc
