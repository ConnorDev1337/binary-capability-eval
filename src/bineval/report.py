"""Load attempt logs and render aggregated results.

Attempts are stored as JSON Lines, one :class:`Attempt` per line, so a runner can append
results as it goes (:func:`append_attempt`) and a crashed run loses at most one line. The
report renders the views from :mod:`bineval.metrics` as Markdown tables, plus a
machine-readable JSON summary for plotting.
"""

from __future__ import annotations

import json
from pathlib import Path

from bineval._version import __version__
from bineval.metrics import Aggregation
from bineval.rubric import Attempt, RubricStep, StepSource, StopReason
from bineval.stats import RateEstimate

# Longest list of unresolved runs printed in the Markdown report; the JSON has them all.
_MAX_LISTED_RUNS = 20


def load_attempts(path: str | Path) -> list[Attempt]:
    """Read a JSONL attempt log. Blank lines are skipped; bad lines raise with a line number."""

    p = Path(path)
    attempts: list[Attempt] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                attempts.append(Attempt.from_dict(json.loads(line)))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ValueError(f"{p}:{lineno}: {exc}") from exc
    return attempts


def write_attempts(path: str | Path, attempts: list[Attempt]) -> None:
    """Write attempts as JSONL (overwrites *path*)."""

    with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
        for a in attempts:
            fh.write(json.dumps(a.to_dict(), sort_keys=True) + "\n")


def append_attempt(path: str | Path, attempt: Attempt) -> None:
    """Append one attempt to a JSONL log, creating it and its directory if needed.

    Pass it as ``evaluate(..., on_attempt=lambda a: append_attempt(log, a))`` so every
    attempt is on disk as soon as it is graded.
    """

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(attempt.to_dict(), sort_keys=True) + "\n")


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _ci(low: float | None, high: float | None) -> str:
    return "-" if low is None or high is None else f"[{_pct(low)}, {_pct(high)}]"


def _signed_pct(x: float) -> str:
    return f"{x * 100:+.1f} pp"


def _count(n: int, total: int) -> str:
    return f"{n} ({_pct(n / total)})" if total else "0"


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out.extend("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join(out)


def markdown_report(agg: Aggregation, *, title: str = "bineval results") -> str:
    """Render an aggregation as a Markdown report."""

    parts: list[str] = [f"# {title}", ""]

    if agg.total_attempts == 0:
        parts.append("_No attempts recorded._")
        return "\n".join(parts) + "\n"

    intro = (
        f"{agg.counted_attempts} graded attempts across {len(agg.models)} model(s) "
        f"and {len(agg.levels)} level(s)."
    )
    if agg.infra_errors:
        intro += (
            f" {agg.infra_errors} attempt(s) that ended in an infrastructure error are "
            "excluded (see below)."
        )
    parts += [intro, ""]
    parts += [
        "Solve rate is the mean over challenges of per-challenge reliability. Intervals treat",
        "challenges, not attempts, as the unit of evidence, because repeated runs of one",
        'challenge are correlated; see `docs/DESIGN.md`, "Uncertainty".',
        "",
    ]

    _capability(parts, agg)
    _stops(parts, agg)
    _failures(parts, agg)
    _comparisons(parts, agg)
    _time(parts, agg)
    _reliability(parts, agg)
    _excluded(parts, agg)

    if agg.warnings:
        parts += ["## Data warnings", ""]
        parts.extend(f"- {w}" for w in agg.warnings)
        parts.append("")

    return "\n".join(parts)


def _capability(parts: list[str], agg: Aggregation) -> None:
    parts += ["## Capability by level", ""]
    rows = [
        [
            s.model,
            s.level,
            str(s.n_challenges),
            str(s.n_attempts),
            _pct(s.solve_rate),
            _ci(s.estimate.ci_low, s.estimate.ci_high),
            "-" if s.estimate.se is None else _pct(s.estimate.se),
            f"{s.challenges_solved_any}/{s.n_challenges} ({_pct(s.coverage)})",
            f"{s.challenges_solved_all}/{s.n_challenges} ({_pct(s.consistency)})",
        ]
        for s in agg.level_summaries
    ]
    header = [
        "model",
        "level",
        "challenges",
        "attempts",
        "solve rate",
        "95% CI",
        "SE",
        "solved >= once",
        "solved every run",
    ]
    parts += [_table(header, rows), ""]


def _stops(parts: list[str], agg: Aggregation) -> None:
    parts += ["## How attempts ended", ""]
    reasons = [r for r in StopReason if r is not StopReason.INFRA_ERROR]
    rows = [
        [
            s.model,
            s.level,
            str(s.n_attempts),
            *[_count(s.stop_counts.get(r, 0), s.n_attempts) for r in reasons],
        ]
        for s in agg.level_summaries
    ]
    parts += [_table(["model", "level", "attempts", *[r.name for r in reasons]], rows), ""]
    if any(s.stop_counts.get(StopReason.REFUSED) for s in agg.level_summaries):
        parts += [
            "Refusals count as unsolved. A refusal hides capability rather than measuring",
            "it, so a level with many refusals is a lower bound on what the model can do.",
            "",
        ]


def _failures(parts: list[str], agg: Aggregation) -> None:
    parts += ["## Where unsolved attempts stopped", ""]
    if not agg.failure_breakdowns:
        parts += ["_No unsolved attempts._", ""]
        return
    steps = [s for s in RubricStep if s is not RubricStep.DELIVER]
    rows = []
    for fb in agg.failure_breakdowns:
        modal = fb.modal_step
        rows.append(
            [
                fb.model,
                fb.level,
                str(fb.total),
                *[_count(fb.counts.get(step, 0), fb.total) for step in steps],
                modal.label if modal is not None else "-",
            ]
        )
    header = ["model", "level", "failures", *[s.name for s in steps], "most common stop"]
    parts += [_table(header, rows), ""]
    graded = agg.step_sources.get(StepSource.CHECKPOINTS, 0)
    claimed = agg.step_sources.get(StepSource.CLAIMED, 0)
    parts += [
        f"Step labels: {graded} attempt(s) from graded checkpoints, {claimed} claimed by the "
        "runner (see `docs/RUBRIC.md`).",
        "",
    ]


def _comparisons(parts: list[str], agg: Aggregation) -> None:
    if not agg.comparisons:
        return
    parts += [
        "## Paired comparison",
        "",
        "Difference in solve rate, first model minus second, over the challenges both",
        "attempted. No interval is shown with fewer than two challenges, or when every",
        "challenge gave the same difference.",
        "",
    ]
    rows = [
        [
            c.level,
            c.model_a,
            c.model_b,
            str(c.result.n_challenges),
            _signed_pct(c.result.diff),
            "-"
            if c.result.ci_low is None or c.result.ci_high is None
            else f"[{_signed_pct(c.result.ci_low)}, {_signed_pct(c.result.ci_high)}]",
        ]
        for c in agg.comparisons
    ]
    parts += [_table(["level", "model A", "model B", "challenges", "A - B", "95% CI"], rows), ""]


def _time(parts: list[str], agg: Aggregation) -> None:
    if not agg.time_buckets:
        return
    parts += ["## Solve rate by estimated human solve time", ""]
    rows = [
        [
            t.model,
            t.bucket,
            str(t.n_challenges),
            str(t.n_attempts),
            _pct(t.estimate.rate),
            _ci(t.estimate.ci_low, t.estimate.ci_high),
        ]
        for t in agg.time_buckets
    ]
    header = ["model", "human time", "challenges", "attempts", "solve rate", "95% CI"]
    parts += [_table(header, rows), ""]


def _reliability(parts: list[str], agg: Aggregation) -> None:
    parts += ["## Reliability per challenge", ""]
    with_time = any(r.human_minutes is not None for r in agg.challenge_results)
    rows = []
    for r in agg.challenge_results:
        row = [r.model, r.level, r.challenge_id]
        if with_time:
            row.append("-" if r.human_minutes is None else f"{r.human_minutes:g}")
        row += [f"{r.solved_count}/{r.runs}", _pct(r.reliability)]
        rows.append(row)
    header = ["model", "level", "challenge"]
    if with_time:
        header.append("human min")
    header += ["solved / runs", "reliability"]
    parts += [_table(header, rows), ""]


def _excluded(parts: list[str], agg: Aggregation) -> None:
    if not agg.infra_errors:
        return
    parts += [
        "## Excluded attempts",
        "",
        f"{agg.infra_errors} attempt(s) ended in `INFRA_ERROR` and are excluded from every "
        "table above.",
        "",
    ]
    if not agg.unresolved_runs:
        parts += ["Every one of those runs was re-run and has a valid result.", ""]
        return
    parts += [
        f"{len(agg.unresolved_runs)} run(s) still have no valid result. Resume the evaluation",
        "(`evaluate(..., done=load_attempts(log))`) to re-run them:",
        "",
    ]
    parts.extend(f"- {r}" for r in agg.unresolved_runs[:_MAX_LISTED_RUNS])
    if len(agg.unresolved_runs) > _MAX_LISTED_RUNS:
        parts.append(f"- ... and {len(agg.unresolved_runs) - _MAX_LISTED_RUNS} more")
    parts.append("")


def _estimate(e: RateEstimate) -> dict:
    return {"rate": e.rate, "se": e.se, "n_eff": e.n_eff, "ci_low": e.ci_low, "ci_high": e.ci_high}


def json_summary(agg: Aggregation) -> dict:
    """Machine-readable summary suitable for plotting or diffing between runs."""

    return {
        "bineval_version": __version__,
        "total_attempts": agg.total_attempts,
        "counted_attempts": agg.counted_attempts,
        "infra_errors": agg.infra_errors,
        "unresolved_runs": list(agg.unresolved_runs),
        "models": list(agg.models),
        "levels": list(agg.levels),
        "step_sources": {s.name: n for s, n in sorted(agg.step_sources.items())},
        "level_summaries": [
            {
                "model": s.model,
                "level": s.level,
                "n_challenges": s.n_challenges,
                "n_attempts": s.n_attempts,
                "solved_attempts": s.solved_attempts,
                "solve_rate": s.solve_rate,
                "solve_rate_estimate": _estimate(s.estimate),
                "challenges_solved_any": s.challenges_solved_any,
                "coverage": s.coverage,
                "challenges_solved_all": s.challenges_solved_all,
                "consistency": s.consistency,
                "stop_counts": {r.name: n for r, n in sorted(s.stop_counts.items())},
            }
            for s in agg.level_summaries
        ],
        "failure_breakdowns": [
            {
                "model": fb.model,
                "level": fb.level,
                "total": fb.total,
                "counts": {step.name: n for step, n in sorted(fb.counts.items())},
                "modal_step": fb.modal_step.name if fb.modal_step is not None else None,
            }
            for fb in agg.failure_breakdowns
        ],
        "comparisons": [
            {
                "level": c.level,
                "model_a": c.model_a,
                "model_b": c.model_b,
                "n_challenges": c.result.n_challenges,
                "diff": c.result.diff,
                "se": c.result.se,
                "ci_low": c.result.ci_low,
                "ci_high": c.result.ci_high,
            }
            for c in agg.comparisons
        ],
        "time_buckets": [
            {
                "model": t.model,
                "bucket": t.bucket,
                "n_challenges": t.n_challenges,
                "n_attempts": t.n_attempts,
                "solve_rate_estimate": _estimate(t.estimate),
            }
            for t in agg.time_buckets
        ],
        "challenge_results": [
            {
                "model": r.model,
                "challenge_id": r.challenge_id,
                "level": r.level,
                "runs": r.runs,
                "solved_count": r.solved_count,
                "reliability": r.reliability,
                "human_minutes": r.human_minutes,
            }
            for r in agg.challenge_results
        ],
        "warnings": list(agg.warnings),
    }
