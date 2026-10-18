"""Command-line interface: ``bineval validate``, ``grade``, ``hash``, ``set-hash``, ``report``."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bineval._version import __version__
from bineval.challenge import challenge_set_hash, load_challenge, load_challenges
from bineval.grader import grade
from bineval.metrics import aggregate
from bineval.report import json_summary, load_attempts, markdown_report, tag_attempts
from bineval.rubric import Attempt


def cmd_validate(args) -> int:
    target = Path(args.path)
    try:
        challenges = load_challenges(target) if target.is_dir() else [load_challenge(target)]
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for ch in challenges:
        print(f"ok  {ch.id:<32} {ch.level.value:<18} grader={ch.grader.kind.value}")
    print(f"{len(challenges)} challenge(s) valid")
    return 0


def cmd_grade(args) -> int:
    try:
        ch = load_challenge(args.challenge)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    submission = sys.stdin.read() if args.submission == "-" else args.submission
    outcome = grade(ch.grader, submission)
    print(f"{'CORRECT' if outcome.correct else 'INCORRECT'}: {outcome.reason}")
    return 0 if outcome.correct else 1


def cmd_hash(args) -> int:
    text = args.answer.strip()
    if args.case_insensitive:
        text = text.lower()
    print(hashlib.sha256(text.encode("utf-8")).hexdigest())
    return 0


def cmd_set_hash(args) -> int:
    try:
        challenges = load_challenges(args.path)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not challenges:
        print(f"error: no challenges found under {args.path}", file=sys.stderr)
        return 1
    print(f"{challenge_set_hash(challenges)}  ({len(challenges)} challenge(s))")
    return 0


def cmd_report(args) -> int:
    if args.tag and len(args.tag) != len(args.attempts):
        print(
            f"error: got {len(args.tag)} --tag value(s) for {len(args.attempts)} log(s); "
            "give one per log or none",
            file=sys.stderr,
        )
        return 2
    attempts: list[Attempt] = []
    try:
        for i, path in enumerate(args.attempts):
            log = load_attempts(path)
            attempts += tag_attempts(log, args.tag[i]) if args.tag else log
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    agg = aggregate(attempts)
    if args.format == "json":
        text = json.dumps(json_summary(agg), indent=2, sort_keys=True) + "\n"
    else:
        text = markdown_report(agg, title=args.title)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bineval",
        description="Measure LLM-agent capability on reverse-engineering tasks.",
    )
    p.add_argument("--version", action="version", version=f"bineval {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a challenge file or a directory of them")
    v.add_argument("path")
    v.set_defaults(func=cmd_validate)

    g = sub.add_parser("grade", help="grade one submission against a challenge")
    g.add_argument("challenge", help="path to the challenge YAML")
    g.add_argument("submission", help="the answer to grade, or '-' to read stdin")
    g.set_defaults(func=cmd_grade)

    h = sub.add_parser("hash", help="print the SHA-256 digest of an answer for a sha256 grader")
    h.add_argument("answer")
    h.add_argument(
        "--case-insensitive",
        action="store_true",
        help="lower-case the answer first (pair with case_sensitive: false)",
    )
    h.set_defaults(func=cmd_hash)

    s = sub.add_parser("set-hash", help="print the challenge-set hash for a directory")
    s.add_argument("path", help="directory of challenge YAML files")
    s.set_defaults(func=cmd_set_hash)

    r = sub.add_parser("report", help="aggregate JSONL attempt logs into a report")
    r.add_argument("attempts", nargs="+", help="one or more JSONL attempt logs, read together")
    r.add_argument(
        "--tag",
        action="append",
        help="label for each log, in order, appended to its model names; tag two logs of "
        "one model (e.g. before/after an elicitation change) to get a paired comparison",
    )
    r.add_argument("--format", choices=["markdown", "json"], default="markdown")
    r.add_argument("--out", help="write to this file instead of stdout")
    r.add_argument("--title", default="bineval results")
    r.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
