"""Load attempt logs and render aggregated results.

Attempts are stored as JSON Lines, one :class:`Attempt` per line, so a runner can append
results as it goes and a crashed run loses at most one line. The report renders the
three views from :mod:`bineval.metrics` as Markdown tables, plus a machine-readable
JSON summary for plotting.
"""

from __future__ import annotations

import json
from pathlib import Path

from bineval.metrics import Aggregation
from bineval.rubric import Attempt, RubricStep


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


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


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

    parts.append(
        f"{agg.total_attempts} attempts across {len(agg.models)} model(s) "
        f"and {len(agg.levels)} level(s)."
    )
    parts.append("")

    # Capability curve by level.
    parts += ["## Capability by level", ""]
    parts.append(
        _table(
            ["model", "level", "challenges", "attempts", "solve rate", "solved >= once"],
            [
                [
                    s.model,
                    s.level,
                    str(s.n_challenges),
                    str(s.n_attempts),
                    _pct(s.solve_rate),
                    f"{s.challenges_solved_any}/{s.n_challenges} ({_pct(s.coverage)})",
                ]
                for s in agg.level_summaries
            ],
        )
    )
    parts.append("")

    # Failure breakdown.
    parts += ["## Where unsolved attempts stopped", ""]
    steps = [s for s in RubricStep if s is not RubricStep.DELIVER]
    if agg.failure_breakdowns:
        rows = []
        for fb in agg.failure_breakdowns:
            cells = [fb.model, str(fb.total)]
            for step in steps:
                n = fb.counts.get(step, 0)
                cells.append(f"{n} ({_pct(n / fb.total)})" if fb.total else "0")
            modal = fb.modal_step
            cells.append(modal.label if modal is not None else "-")
            rows.append(cells)
        header = ["model", "failures", *[s.name for s in steps], "most common stop"]
        parts.append(_table(header, rows))
    else:
        parts.append("_No unsolved attempts._")
    parts.append("")

    # Per-challenge reliability.
    parts += ["## Reliability per challenge", ""]
    parts.append(
        _table(
            ["model", "level", "challenge", "solved / runs", "reliability"],
            [
                [
                    r.model,
                    r.level,
                    r.challenge_id,
                    f"{r.solved_count}/{r.runs}",
                    _pct(r.reliability),
                ]
                for r in agg.challenge_results
            ],
        )
    )
    parts.append("")

    if agg.warnings:
        parts += ["## Data warnings", ""]
        parts.extend(f"- {w}" for w in agg.warnings)
        parts.append("")

    return "\n".join(parts)


def json_summary(agg: Aggregation) -> dict:
    """Machine-readable summary suitable for plotting or diffing between runs."""

    return {
        "total_attempts": agg.total_attempts,
        "models": list(agg.models),
        "levels": list(agg.levels),
        "level_summaries": [
            {
                "model": s.model,
                "level": s.level,
                "n_challenges": s.n_challenges,
                "n_attempts": s.n_attempts,
                "solved_attempts": s.solved_attempts,
                "solve_rate": s.solve_rate,
                "challenges_solved_any": s.challenges_solved_any,
                "coverage": s.coverage,
            }
            for s in agg.level_summaries
        ],
        "failure_breakdowns": [
            {
                "model": fb.model,
                "total": fb.total,
                "counts": {step.name: n for step, n in sorted(fb.counts.items())},
                "modal_step": fb.modal_step.name if fb.modal_step is not None else None,
            }
            for fb in agg.failure_breakdowns
        ],
        "challenge_results": [
            {
                "model": r.model,
                "challenge_id": r.challenge_id,
                "level": r.level,
                "runs": r.runs,
                "solved_count": r.solved_count,
                "reliability": r.reliability,
            }
            for r in agg.challenge_results
        ],
        "warnings": list(agg.warnings),
    }
