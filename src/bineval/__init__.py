"""bineval - measure how far an autonomous LLM agent gets on reverse-engineering
and binary-analysis tasks, by difficulty and by the sub-step where it fails.

This package is the *measurement* side only: a challenge schema, a self-validating
grader, a per-sub-step rubric, aggregation into capability/reliability metrics, and a
report renderer. It ships no exploits and no offensive agent; the agent runner and the
sandbox are interfaces you implement for your own isolated environment.
"""

from __future__ import annotations

from bineval._version import __version__
from bineval.challenge import (
    Challenge,
    Checkpoint,
    GraderSpec,
    Level,
    challenge_set_hash,
    load_challenge,
    load_challenges,
)
from bineval.grader import GradeOutcome, grade
from bineval.metrics import (
    ChallengeResult,
    FailureBreakdown,
    LevelSummary,
    ModelComparison,
    aggregate,
)
from bineval.report import append_attempt, load_attempts, tag_attempts
from bineval.rubric import Attempt, RubricStep, StepSource, StopReason
from bineval.runner import AgentRunner, RunOutput, evaluate

__all__ = [
    "AgentRunner",
    "Attempt",
    "Challenge",
    "ChallengeResult",
    "Checkpoint",
    "FailureBreakdown",
    "GradeOutcome",
    "GraderSpec",
    "Level",
    "LevelSummary",
    "ModelComparison",
    "RubricStep",
    "RunOutput",
    "StepSource",
    "StopReason",
    "__version__",
    "aggregate",
    "append_attempt",
    "challenge_set_hash",
    "evaluate",
    "grade",
    "load_attempts",
    "load_challenge",
    "load_challenges",
    "tag_attempts",
]
