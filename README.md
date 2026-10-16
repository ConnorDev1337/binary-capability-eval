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
- Aggregation into a capability curve by difficulty, a failure table by model, and
  reliability figures from repeated runs.

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
furthest rubric step reached. Runs are repeated `k` times per challenge because results
vary; reliability is reported alongside the raw solve rate.

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
bineval report examples/attempts.synthetic.jsonl        # Markdown report
bineval report examples/attempts.synthetic.jsonl --format json --out summary.json
```

`examples/attempts.synthetic.jsonl` is **synthetic demo data** for exercising the report.
It is not a measurement of any model.

## Plugging in a runner

bineval does not ship an agent. Implement the `AgentRunner` protocol for your model and
your sandbox, and `evaluate()` does the rest:

```python
from bineval import RubricStep, RunOutput, evaluate, load_challenges
from bineval.report import write_attempts

class MyRunner:
    model = "my-model-2026-10-01"

    def run(self, challenge, run_index):
        # Drive your agent inside your isolated VM; return its answer and how far it got.
        return RunOutput(submission="...", furthest_step=RubricStep.READ_ASSEMBLY)

attempts = evaluate(load_challenges("challenges/"), MyRunner(), k=3)
write_attempts("runs/my-model.jsonl", attempts)
```

The grader decides whether an attempt is solved. `evaluate()` overrides the runner's
claimed step to keep it consistent with the grade, so a runner cannot inflate its score.

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

Alpha. The measurement side is complete and tested: challenge schema, grading, rubric,
evaluation loop, metrics, and reporting. No results are published yet. The agent runner
and sandbox are interfaces you implement for your own environment.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
