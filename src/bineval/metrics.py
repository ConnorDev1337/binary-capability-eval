"""Aggregate attempts into capability and reliability metrics.

These views come out of a flat list of :class:`Attempt` records:

* **Per-challenge reliability** - of the ``k`` repeated runs, how many were solved.
  Capability on a binary varies run to run, so a single run overstates or understates
  it; reliability makes that variance explicit.
* **Per-level summary** - the capability curve by difficulty: the solve rate with a 95%
  interval, how many challenges were solved at least once and on every run, and how the
  attempts ended (answered, refused, out of budget, no answer).
* **Failure breakdown per model and level** - among *unsolved* attempts, a histogram over
  the furthest rubric step reached. This is the "where does it get stuck" table. It is
  split by level because the mix of challenges otherwise dominates it.
* **Paired comparisons** - the difference between two models at a level, paired by
  challenge.
* **Solve rate by estimated human solve time**, for challenges that record one.

Attempts that ended in ``INFRA_ERROR`` say nothing about the model. They are excluded
from every view above and counted separately.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from bineval.challenge import Level
from bineval.rubric import Attempt, RubricStep, StepSource, StopReason
from bineval.stats import PairedDifference, RateEstimate, estimate_rate, paired_difference

# Upper bounds (exclusive) in minutes, and labels, for the human-time view.
TIME_BUCKETS: tuple[tuple[float, str], ...] = (
    (15, "< 15 min"),
    (60, "15-60 min"),
    (240, "1-4 h"),
    (math.inf, ">= 4 h"),
)


def level_sort_key(level: str) -> tuple[int, str]:
    """Order known levels by difficulty; unknown labels sort after, alphabetically."""

    try:
        return (Level(level).rank, level)
    except ValueError:
        return (len(Level), level)


def time_bucket(minutes: float) -> str:
    """The :data:`TIME_BUCKETS` label for an estimated human solve time."""

    return next(label for bound, label in TIME_BUCKETS if minutes < bound)


@dataclass(frozen=True)
class ChallengeResult:
    """Outcome of one model on one challenge, across its repeated runs."""

    model: str
    challenge_id: str
    level: str
    runs: int
    solved_count: int
    human_minutes: float | None = None

    @property
    def reliability(self) -> float:
        """Fraction of runs that were solved (0.0 .. 1.0)."""

        return self.solved_count / self.runs if self.runs else 0.0

    @property
    def solved_any(self) -> bool:
        return self.solved_count > 0

    @property
    def solved_all(self) -> bool:
        return self.runs > 0 and self.solved_count == self.runs


@dataclass(frozen=True)
class LevelSummary:
    """A model's aggregate performance at one difficulty level."""

    model: str
    level: str
    n_challenges: int
    n_attempts: int
    solved_attempts: int
    challenges_solved_any: int
    challenges_solved_all: int
    estimate: RateEstimate
    stop_counts: dict[StopReason, int] = field(default_factory=dict)

    @property
    def solve_rate(self) -> float:
        """Mean over challenges of per-challenge reliability."""

        return self.estimate.rate

    @property
    def coverage(self) -> float:
        """Fraction of challenges solved on at least one run (a pass@k-style view)."""

        return self.challenges_solved_any / self.n_challenges if self.n_challenges else 0.0

    @property
    def consistency(self) -> float:
        """Fraction of challenges solved on every run (a pass^k-style view)."""

        return self.challenges_solved_all / self.n_challenges if self.n_challenges else 0.0

    @property
    def refusal_rate(self) -> float:
        n = self.stop_counts.get(StopReason.REFUSED, 0)
        return n / self.n_attempts if self.n_attempts else 0.0


@dataclass(frozen=True)
class FailureBreakdown:
    """Where a model's *unsolved* attempts at one level got stuck, as a step histogram."""

    model: str
    level: str
    counts: dict[RubricStep, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def modal_step(self) -> RubricStep | None:
        """The most common furthest step among failures, or ``None`` if no failures."""

        if not self.counts:
            return None
        return max(self.counts.items(), key=lambda kv: (kv[1], kv[0].value))[0]


@dataclass(frozen=True)
class ModelComparison:
    """``model_a`` minus ``model_b`` at one level, paired by challenge."""

    level: str
    model_a: str
    model_b: str
    result: PairedDifference


@dataclass(frozen=True)
class TimeBucketSummary:
    """A model's solve rate on challenges in one estimated-human-time bucket."""

    model: str
    bucket: str
    n_challenges: int
    n_attempts: int
    estimate: RateEstimate


@dataclass(frozen=True)
class Aggregation:
    """The full aggregated view over a set of attempts."""

    models: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    challenge_results: tuple[ChallengeResult, ...] = ()
    level_summaries: tuple[LevelSummary, ...] = ()
    failure_breakdowns: tuple[FailureBreakdown, ...] = ()
    comparisons: tuple[ModelComparison, ...] = ()
    time_buckets: tuple[TimeBucketSummary, ...] = ()
    total_attempts: int = 0
    """Every record read, including excluded ones."""

    infra_errors: int = 0
    unresolved_runs: tuple[str, ...] = ()
    """Runs whose only records are ``INFRA_ERROR``: they still need a valid result."""

    step_sources: dict[StepSource, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def counted_attempts(self) -> int:
        return self.total_attempts - self.infra_errors


def aggregate(attempts: list[Attempt]) -> Aggregation:
    """Fold *attempts* into per-challenge, per-level, and per-model summaries."""

    if not attempts:
        return Aggregation()

    warnings: list[str] = []
    counted = [a for a in attempts if a.counted]
    errors = [a for a in attempts if not a.counted]

    level_of: dict[str, str] = {}
    for a in attempts:
        prev = level_of.setdefault(a.challenge_id, a.level)
        if prev != a.level:
            warnings.append(
                f"challenge {a.challenge_id!r} appears under levels {prev!r} and {a.level!r}"
            )

    minutes_of: dict[str, float] = {}
    for a in attempts:
        if a.human_minutes is None:
            continue
        prev_minutes = minutes_of.setdefault(a.challenge_id, a.human_minutes)
        if prev_minutes != a.human_minutes:
            warnings.append(
                f"challenge {a.challenge_id!r} has human_minutes {prev_minutes} "
                f"and {a.human_minutes}"
            )

    have = {(a.model, a.challenge_id, a.run_index) for a in counted}
    unresolved = sorted(
        {(a.model, a.challenge_id, a.run_index) for a in errors} - have,
    )

    # Per (model, challenge) rollup.
    by_mc: dict[tuple[str, str], list[Attempt]] = defaultdict(list)
    for a in counted:
        by_mc[(a.model, a.challenge_id)].append(a)

    challenge_results: list[ChallengeResult] = []
    for (model, cid), runs in by_mc.items():
        seen_idx = [r.run_index for r in runs]
        if len(set(seen_idx)) != len(seen_idx):
            warnings.append(f"{model}/{cid}: duplicate run_index values {sorted(seen_idx)}")
        challenge_results.append(
            ChallengeResult(
                model=model,
                challenge_id=cid,
                level=level_of[cid],
                runs=len(runs),
                solved_count=sum(1 for r in runs if r.solved),
                human_minutes=minutes_of.get(cid),
            )
        )
    challenge_results.sort(key=lambda r: (r.model, level_sort_key(r.level), r.challenge_id))

    # Per (model, level) rollup.
    attempts_by_ml: dict[tuple[str, str], list[Attempt]] = defaultdict(list)
    for a in counted:
        attempts_by_ml[(a.model, level_of[a.challenge_id])].append(a)
    results_by_ml: dict[tuple[str, str], list[ChallengeResult]] = defaultdict(list)
    for r in challenge_results:
        results_by_ml[(r.model, r.level)].append(r)

    level_summaries: list[LevelSummary] = []
    failure_breakdowns: list[FailureBreakdown] = []
    for (model, level), ml_attempts in attempts_by_ml.items():
        ml_results = results_by_ml[(model, level)]
        run_counts = {r.runs for r in ml_results}
        if len(run_counts) > 1:
            warnings.append(
                f"{model}/{level}: challenges have between {min(run_counts)} and "
                f"{max(run_counts)} valid runs"
            )
        level_summaries.append(
            LevelSummary(
                model=model,
                level=level,
                n_challenges=len(ml_results),
                n_attempts=len(ml_attempts),
                solved_attempts=sum(1 for a in ml_attempts if a.solved),
                challenges_solved_any=sum(1 for r in ml_results if r.solved_any),
                challenges_solved_all=sum(1 for r in ml_results if r.solved_all),
                estimate=estimate_rate([r.reliability for r in ml_results], len(ml_attempts)),
                stop_counts=dict(Counter(a.stop_reason for a in ml_attempts)),
            )
        )
        fails = Counter(a.furthest_step for a in ml_attempts if not a.solved)
        if fails:
            failure_breakdowns.append(FailureBreakdown(model, level, dict(fails)))
    level_summaries.sort(key=lambda s: (s.model, level_sort_key(s.level)))
    failure_breakdowns.sort(key=lambda f: (f.model, level_sort_key(f.level)))

    models = tuple(sorted({a.model for a in attempts}))
    levels = tuple(sorted({level_of[a.challenge_id] for a in attempts}, key=level_sort_key))

    return Aggregation(
        models=models,
        levels=levels,
        challenge_results=tuple(challenge_results),
        level_summaries=tuple(level_summaries),
        failure_breakdowns=tuple(failure_breakdowns),
        comparisons=tuple(_comparisons(challenge_results, models, levels)),
        time_buckets=tuple(_time_buckets(challenge_results, models)),
        total_attempts=len(attempts),
        infra_errors=len(errors),
        unresolved_runs=tuple(f"{m}/{cid} run {i}" for m, cid, i in unresolved),
        step_sources=dict(Counter(a.step_source for a in counted)),
        warnings=tuple(warnings),
    )


def _comparisons(
    results: list[ChallengeResult], models: tuple[str, ...], levels: tuple[str, ...]
) -> list[ModelComparison]:
    reliability = {(r.model, r.challenge_id): r.reliability for r in results}
    ids_by_level: dict[str, set[str]] = defaultdict(set)
    for r in results:
        ids_by_level[r.level].add(r.challenge_id)
    out: list[ModelComparison] = []
    for level in levels:
        for a, b in itertools.combinations(models, 2):
            shared = sorted(
                cid
                for cid in ids_by_level[level]
                if (a, cid) in reliability and (b, cid) in reliability
            )
            if not shared:
                continue
            result = paired_difference(
                [reliability[(a, cid)] for cid in shared],
                [reliability[(b, cid)] for cid in shared],
            )
            out.append(ModelComparison(level, a, b, result))
    return out


def _time_buckets(
    results: list[ChallengeResult], models: tuple[str, ...]
) -> list[TimeBucketSummary]:
    grouped: dict[tuple[str, str], list[ChallengeResult]] = defaultdict(list)
    for r in results:
        if r.human_minutes is not None:
            grouped[(r.model, time_bucket(r.human_minutes))].append(r)
    out: list[TimeBucketSummary] = []
    for model in models:
        for _, label in TIME_BUCKETS:
            rs = grouped.get((model, label))
            if not rs:
                continue
            n_attempts = sum(r.runs for r in rs)
            out.append(
                TimeBucketSummary(
                    model=model,
                    bucket=label,
                    n_challenges=len(rs),
                    n_attempts=n_attempts,
                    estimate=estimate_rate([r.reliability for r in rs], n_attempts),
                )
            )
    return out
