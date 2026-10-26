# Threat model

This project measures a dual-use capability. This document states what could go wrong, what the repository does about it, and what is left to whoever runs it.

## What is published

- The measurement library (schema, grader, rubric, metrics, report).
- Challenge **metadata** and grader specs, with answers stored as digests where they should not be public.
- Aggregate results and analysis.

## What is never published

- Exploits, payloads, or solution scripts.
- A working offensive agent or agent prompts tuned for exploitation.
- Binaries. `.gitignore` excludes them, and the repository hygiene tests check that no executable formats are committed.
- `FULL_EXPLOITATION` challenge content of any kind.
- Checkpoint questions for `VULN_DETECTION` and `FULL_EXPLOITATION` challenges: a question such as "which instruction overruns the buffer" locates the flaw by itself.
- Raw agent transcripts from `VULN_DETECTION` or `FULL_EXPLOITATION` runs. Publish per-step counts instead.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Repository becomes a how-to for attacking binaries. | Measurement code only; no solutions, transcripts, or agent prompts at the sensitive levels. |
| Agent escapes the sandbox or reaches real systems during a run. | Runs happen in a VM with no network, no shared folders, and no credentials. Snapshot and revert after each run. |
| Agent targets something other than the toy binary. | Only binaries you built yourself are present in the VM. Nothing else is reachable. |
| Results are mistaken for an exploit success on real software. | Every result is labelled with the challenge set, runner, and sandbox; toy binaries are described as toy binaries. |
| Contaminated challenges inflate scores. | Use your own unpublished challenges; do not bundle public CTF sets. |
| Leaked answers make the set useless. | `sha256` graders store only digests. |
| Self-reported progress inflates scores. | The grader alone decides `DELIVER`; `evaluate()` overrides runner claims, and checkpoints replace claimed steps where defined. |
| A runner error leaks transcript text into a published log. | Exception notes are cut to 200 characters; still review `notes` before publishing a log. |
| Refusals or outages are read as low capability. | Each attempt records its stop reason; infrastructure errors are excluded and refusals reported separately. |

## Lab requirements for running evaluations

- An isolated VM (or equivalent) with networking disabled at the hypervisor level.
- No host mounts, clipboard sharing, or credentials inside the guest.
- Only your own toy binaries inside the guest.
- Resource and time limits on every run.
- A clean snapshot restored between runs.

## Disclosure

If an evaluation suggests a model can do something materially more dangerous than expected, report it to the model developer through their published responsible-disclosure or safety-reporting channel before publishing details, and publish only aggregate results.
