# challenges/

Your own challenges live here. **None are shipped.**

Each challenge is a YAML file in the format of
[`examples/asm-reading-001.yaml`](../examples/asm-reading-001.yaml). Validate them with:

```
bineval validate challenges/
```

Binaries are never committed: `.gitignore` excludes `challenges/**/bin/`, `*.elf`, and
`*.out`. Build them yourself, inside the isolated lab described in
[`docs/THREAT_MODEL.md`](../docs/THREAT_MODEL.md).

Do not copy in third-party challenge sets that have academic-integrity rules or public
write-ups. They contaminate the measurement (models have likely seen the solutions) and
redistributing them may break their terms.
