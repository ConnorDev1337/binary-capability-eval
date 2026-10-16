"""bineval - measure how far an autonomous LLM agent gets on reverse-engineering
and binary-analysis tasks, by difficulty and by the sub-step where it fails.

This package is the *measurement* side only: a challenge schema, a self-validating
grader, a per-sub-step rubric, aggregation into capability/reliability metrics, and a
report renderer. It ships no exploits and no offensive agent; the agent runner and the
sandbox are interfaces you implement for your own isolated environment.
"""

from __future__ import annotations

from bineval.challenge import (
    Challenge,
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
    aggregate,
)
from bineval.rubric import Attempt, RubricStep
from bineval.runner import AgentRunner, RunOutput, evaluate

__all__ = [
    "AgentRunner",
    "Attempt",
    "Challenge",
    "ChallengeResult",
    "FailureBreakdown",
    "GradeOutcome",
    "GraderSpec",
    "Level",
    "LevelSummary",
    "RubricStep",
    "RunOutput",
    "aggregate",
    "challenge_set_hash",
    "evaluate",
    "grade",
    "load_challenge",
    "load_challenges",
]

__version__ = "0.1.0"
