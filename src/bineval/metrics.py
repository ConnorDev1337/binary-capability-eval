"""Aggregate attempts into capability and reliability metrics.

Three views come out of a flat list of :class:`Attempt` records:

* **Per-challenge reliability** - of the ``k`` repeated runs, how many were solved.
  Capability on a binary varies run to run, so a single run overstates or understates
  it; reliability makes that variance explicit.
* **Per-level summary** - the capability curve by difficulty: solve rate across all
  attempts at a level, plus how many distinct challenges were solved at least once.
* **Per-model failure breakdown** - among *unsolved* attempts, a histogram over the
  furthest rubric step reached. This is the "where does it get stuck" table.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from bineval.challenge import Level
from bineval.rubric import Attempt, RubricStep


def level_sort_key(level: str) -> tuple[int, str]:
    """Order known levels by difficulty; unknown labels sort after, alphabetically."""

    try:
        return (Level(level).rank, level)
    except ValueError:
        return (len(Level), level)


@dataclass(frozen=True)
class ChallengeResult:
    """Outcome of one model on one challenge, across its repeated runs."""

    model: str
    challenge_id: str
    level: str
    runs: int
    solved_count: int

    @property
    def reliability(self) -> float:
        """Fraction of runs that were solved (0.0 .. 1.0)."""

        return self.solved_count / self.runs if self.runs else 0.0

    @property
    def solved_any(self) -> bool:
        return self.solved_count > 0


@dataclass(frozen=True)
class LevelSummary:
    """A model's aggregate performance at one difficulty level."""

    model: str
    level: str
    n_challenges: int
    n_attempts: int
    solved_attempts: int
    challenges_solved_any: int

    @property
    def solve_rate(self) -> float:
        """Solved attempts over all attempts at this level."""

        return self.solved_attempts / self.n_attempts if self.n_attempts else 0.0

    @property
    def coverage(self) -> float:
        """Fraction of challenges solved on at least one run."""

        return self.challenges_solved_any / self.n_challenges if self.n_challenges else 0.0


@dataclass(frozen=True)
class FailureBreakdown:
    """Where a model's *unsolved* attempts got stuck, as a step histogram."""

    model: str
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
class Aggregation:
    """The full aggregated view over a set of attempts."""

    models: tuple[str, ...]
    levels: tuple[str, ...]
    challenge_results: tuple[ChallengeResult, ...]
    level_summaries: tuple[LevelSummary, ...]
    failure_breakdowns: tuple[FailureBreakdown, ...]
    total_attempts: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def aggregate(attempts: list[Attempt]) -> Aggregation:
    """Fold *attempts* into per-challenge, per-level, and per-model summaries."""

    if not attempts:
        return Aggregation((), (), (), (), (), 0, ())

    warnings: list[str] = []

    # Per (model, challenge) rollup.
    by_mc: dict[tuple[str, str], list[Attempt]] = defaultdict(list)
    level_of: dict[str, str] = {}
    for a in attempts:
        by_mc[(a.model, a.challenge_id)].append(a)
        prev = level_of.setdefault(a.challenge_id, a.level)
        if prev != a.level:
            warnings.append(
                f"challenge {a.challenge_id!r} appears under levels {prev!r} and {a.level!r}"
            )

    challenge_results: list[ChallengeResult] = []
    for (model, cid), runs in by_mc.items():
        solved = sum(1 for r in runs if r.solved)
        seen_idx = [r.run_index for r in runs]
        if len(set(seen_idx)) != len(seen_idx):
            warnings.append(f"{model}/{cid}: duplicate run_index values {sorted(seen_idx)}")
        challenge_results.append(
            ChallengeResult(
                model=model,
                challenge_id=cid,
                level=level_of[cid],
                runs=len(runs),
                solved_count=solved,
            )
        )
    challenge_results.sort(key=lambda r: (r.model, level_sort_key(r.level), r.challenge_id))

    # Per (model, level) rollup, built from attempts and challenge results.
    attempts_by_ml: dict[tuple[str, str], list[Attempt]] = defaultdict(list)
    for a in attempts:
        attempts_by_ml[(a.model, a.level)].append(a)

    results_by_ml: dict[tuple[str, str], list[ChallengeResult]] = defaultdict(list)
    for r in challenge_results:
        results_by_ml[(r.model, r.level)].append(r)

    level_summaries: list[LevelSummary] = []
    for (model, level), ml_attempts in attempts_by_ml.items():
        ml_results = results_by_ml[(model, level)]
        level_summaries.append(
            LevelSummary(
                model=model,
                level=level,
                n_challenges=len(ml_results),
                n_attempts=len(ml_attempts),
                solved_attempts=sum(1 for a in ml_attempts if a.solved),
                challenges_solved_any=sum(1 for r in ml_results if r.solved_any),
            )
        )
    level_summaries.sort(key=lambda s: (s.model, level_sort_key(s.level)))

    # Per-model failure breakdown over unsolved attempts.
    fail_counts: dict[str, Counter] = defaultdict(Counter)
    for a in attempts:
        if not a.solved:
            fail_counts[a.model][a.furthest_step] += 1
    failure_breakdowns = [FailureBreakdown(model=m, counts=dict(c)) for m, c in fail_counts.items()]
    failure_breakdowns.sort(key=lambda f: f.model)

    models = tuple(sorted({a.model for a in attempts}))
    levels = tuple(sorted({a.level for a in attempts}, key=level_sort_key))

    return Aggregation(
        models=models,
        levels=levels,
        challenge_results=tuple(challenge_results),
        level_summaries=tuple(level_summaries),
        failure_breakdowns=tuple(failure_breakdowns),
        total_attempts=len(attempts),
        warnings=tuple(warnings),
    )
