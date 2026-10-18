# binary-capability-eval

A reproducible harness for **measuring** how far an autonomous LLM agent gets on
reverse-engineering and binary-analysis tasks without human help, and for pinpointing
the exact sub-step where it fails.

This is a *dangerous-capability evaluation*, in the same spirit as the cybersecurity
evaluations published by frontier-model safety teams. The question is not "can I exploit
this binary?" It is "how far does an LLM agent get on its own, and where does it get
stuck?" The output of this project is a measurement: solve rates by difficulty, a
breakdown of where models fail, and an honest account of the limits.

## What this is

- A schema for challenges, graded automatically (an answer validates itself, usually by
  the task emitting a known flag).
- A per-sub-step rubric that records *where* an attempt failed (read the assembly,
  reason about memory, locate the flaw, build the solution, deliver it), not just a
  binary solved / not-solved.
- Optional graded checkpoints per challenge, so "where it failed" can be measured rather
  than judged.
- Aggregation into a capability curve by difficulty with 95% intervals that account for
  repeated runs, a failure table by model and level, paired model comparisons, and
  reliability figures from repeated runs.
- A record of why each attempt ended, so refusals and infrastructure failures are not
  read as capability limits.

## What this is not

- It does not ship reusable exploits. It publishes the measurement harness, the scores,
  and the analysis.
- It does not include a ready-made offensive agent. The agent interface is abstract; you
  bring your own runner.
- It does not bundle third-party challenge sets with academic-integrity rules (for
  example pwn.college). Those are for your own study, not for a public dataset, and
  bundling them would contaminate the evaluation because models have likely trained on
  their write-ups.

## Design

Challenges are organised by level:

1. **ASM_READING** - read assembly, explain what a function does.
2. **SIMPLE_REVERSING** - find a key or a condition.
3. **VULN_DETECTION** - locate a flaw without exploiting it.
4. **FULL_EXPLOITATION** - end-to-end, only in your own isolated lab with your own
   toy binaries.

Each challenge carries a self-validating grader. Each attempt is annotated with the
furthest rubric step reached and the reason it ended. Runs are repeated `k` times per
challenge because results vary; reliability is reported alongside the solve rate, and
every rate comes with an interval computed over challenges, not attempts.

See [`docs/DESIGN.md`](docs/DESIGN.md), [`docs/RUBRIC.md`](docs/RUBRIC.md), and
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Safety and framing

- Everything runs in an isolated VM with no network, on toy binaries you build yourself.
- The repository publishes the harness, the scores, and the analysis. It does not
  publish reusable offensive tooling.
- The goal is to measure and bound capabilities so defenders can plan. That is the same
  framing used by published dangerous-capability cybersecurity evaluations.

## Quickstart

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip

bineval validate examples/                              # check challenge files
bineval grade examples/asm-reading-001.yaml popcount    # exit 0 if correct, 1 if not
bineval hash --case-insensitive popcount                # digest for a sha256 grader
bineval set-hash examples/                              # challenge-set hash to publish with results
bineval report examples/attempts.synthetic.jsonl        # Markdown report
bineval report examples/attempts.synthetic.jsonl --format json --out summary.json
```

`examples/attempts.synthetic.jsonl` is **synthetic demo data** for exercising the report,
including a refusal, a budget overrun, and an infrastructure error that was re-run. It is
not a measurement of any model.

`bineval report` reads several logs together, for example one per model. To compare two
logs of the same model, such as before and after an elicitation change, tag each one:

```
bineval report runs/base.jsonl runs/tuned.jsonl --tag base --tag tuned
```

The model then appears once per tag (`my-model [base]`, `my-model [tuned]`), and the
paired-comparison table gives the difference challenge by challenge. Models sort by name,
so "model A" in that table is the tag that sorts first.

## Plugging in a runner

bineval does not ship an agent. Implement the `AgentRunner` protocol for your model and
your sandbox, and `evaluate()` does the rest:

```python
from pathlib import Path

from bineval import (
    RubricStep, RunOutput, StopReason, append_attempt, evaluate, load_attempts, load_challenges,
)

class MyRunner:
    model = "my-model-2026-10-01"

    def run(self, challenge, run_index):
        # Drive your agent inside your isolated VM. Return its answer, why it stopped, how
        # far it got, and its answers to the challenge's checkpoint questions, if any.
        return RunOutput(
            submission="...",
            stop_reason=StopReason.ANSWERED,  # or REFUSED, BUDGET_EXHAUSTED, NO_ANSWER
            furthest_step=RubricStep.READ_ASSEMBLY,
            checkpoint_answers={"output-for-0xff": "8"},
        )

log = Path("runs/my-model.jsonl")
done = load_attempts(log) if log.exists() else []
evaluate(
    load_challenges("challenges/"),
    MyRunner(),
    k=3,
    done=done,                                   # resume: skip runs already in the log
    on_attempt=lambda a: append_attempt(log, a),  # every attempt is on disk once graded
)
```

The grader decides whether an attempt is solved, and `evaluate()` keeps the claimed step
consistent with the grade, so a runner cannot inflate its score. For a challenge with
checkpoints, the step comes from grading the checkpoint answers and the claim is ignored.

If the runner raises, the attempt is recorded as `INFRA_ERROR` and the loop moves on.
Those attempts are excluded from every metric, and running the same code again re-runs
them. Report `INFRA_ERROR` yourself for failures that are not the model's.

## Layout

```
binary-capability-eval/
  src/bineval/        measurement library (challenge, grader, rubric, runner, metrics, report, cli)
  challenges/         your own challenges live here (none shipped)
  examples/           a metadata-only example challenge and a synthetic attempt log
  docs/               design, rubric, threat model
  tests/              unit tests for the measurement side, plus repository hygiene checks
```

## Status

Alpha. The measurement side is complete and tested: challenge schema, grading,
checkpoints, rubric, evaluation loop with resume, metrics with uncertainty, and reporting. No results are published yet. The agent runner
and sandbox are interfaces you implement for your own environment.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
