# Design

## Goal

Measure, reproducibly, how far an autonomous LLM agent gets on reverse-engineering and
binary-analysis tasks without human help, and record the sub-step where each failed
attempt stopped. The output is a measurement: solve rates by difficulty, a failure
breakdown by model, and reliability across repeated runs.

## Non-goals

- Shipping exploits, payloads, or a working offensive agent.
- Redistributing third-party challenge sets.
- Ranking models on a leaderboard. The numbers only mean something next to the
  challenge set, the runner, and the sandbox that produced them.

## Components

```
challenge YAML ---> Challenge --+
                                +--> evaluate() --> Attempt (JSONL) --> aggregate() --> report
your AgentRunner --> RunOutput -+        |
                                         +-- grade(): the grader decides "solved"
```

| Module | Role |
|---|---|
| `challenge.py` | Schema (`Challenge`, `GraderSpec`, `Level`) and YAML loading with validation. |
| `grader.py` | Self-validating grader: `exact`, `regex` (full match), `sha256` (digest only). |
| `rubric.py` | Ordered `RubricStep`s and the `Attempt` record. See [RUBRIC.md](RUBRIC.md). |
| `runner.py` | `AgentRunner` protocol (you implement it) and the `evaluate()` loop. |
| `metrics.py` | Aggregation into per-challenge, per-level, and per-model views. |
| `report.py` | JSONL attempt I/O, Markdown report, JSON summary. |
| `cli.py` | `bineval validate`, `grade`, `hash`, `report`. |

## Challenges

A challenge is metadata plus a grader. It does not point at a committed binary: binaries
are built locally inside the lab and are excluded by `.gitignore`. The example in
[`examples/asm-reading-001.yaml`](../examples/asm-reading-001.yaml) shows every field.

Levels, from least to most sensitive:

1. `ASM_READING` - explain what a piece of code does.
2. `SIMPLE_REVERSING` - recover a key or a condition.
3. `VULN_DETECTION` - locate a flaw without exploiting it.
4. `FULL_EXPLOITATION` - end-to-end, only on your own toy binaries in your own isolated
   lab. Challenges at this level are never published with the repository.

### Graders

Grading is automatic so results are reproducible and cheap to re-run. Prefer `sha256`
for anything whose answer should not appear in the repository: the YAML stores only the
digest, and `bineval hash` produces it.

## Attempts and reliability

Each (model, challenge) pair is run `k` times (default 3). Model behaviour varies run to
run, so a single run can overstate or understate capability. The report gives both the
solve rate across all attempts and per-challenge reliability (`solved / runs`).

The runner reports a submission and a claimed furthest step. `evaluate()` grades the
submission and reconciles the claim: a correct answer is recorded as `DELIVER`, and an
incorrect answer can never be recorded as `DELIVER`. A runner cannot raise its own score.

Attempts are written as JSON Lines so a runner can append as it goes and a crash loses at
most one record.

## Metrics

| Metric | Definition |
|---|---|
| Solve rate (per model, level) | solved attempts / all attempts at that level |
| Coverage (per model, level) | challenges solved on at least one run / challenges at that level |
| Reliability (per model, challenge) | solved runs / runs |
| Failure breakdown (per model) | histogram of `furthest_step` over unsolved attempts |

Coverage is a pass@k-style upper view; solve rate is the expected single-run view. Report
both: a large gap between them means capability exists but is unreliable.

## Reproducibility checklist

Record alongside every published result:

- Exact model identifier and version, sampling parameters, and the date of the run.
- `k`, and the runner's tool set, turn budget, and time budget.
- Sandbox image digest.
- The bineval version and the challenge-set hash (not the challenges themselves, if
  they are private).

## Contamination

Public CTF sets and their write-ups are very likely in training data, so solving them
partly measures recall. Use challenges you wrote yourself and have not published.
When you do publish results, consider publishing challenge metadata and digests only, so
the set stays usable for later evaluations.

## Related work

This harness sits alongside published agentic cybersecurity benchmarks such as
InterCode-CTF (2023), NYU CTF Bench (2024), and Cybench (2024). Its emphasis is narrower:
binary analysis specifically, graded by sub-step, with run-to-run reliability as a
first-class output.
