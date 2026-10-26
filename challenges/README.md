# challenges/

Your own challenges live here. **None are shipped.**

Each challenge is a YAML file in the format of [`examples/asm-reading-001.yaml`](../examples/asm-reading-001.yaml). Validate them with:

```
bineval validate challenges/
```

Everything in this directory except this README is gitignored, so your challenges and the binaries you build for them stay out of the repository. That also means git is not your backup: keep the set in a private location of its own. Build binaries yourself, inside the isolated lab described in [`docs/THREAT_MODEL.md`](../docs/THREAT_MODEL.md).

Record the set's hash with each run, and publish it with the results:

```
bineval set-hash challenges/
```

Do not copy in third-party challenge sets that have academic-integrity rules or public write-ups. They contaminate the measurement (models have likely seen the solutions) and redistributing them may break their terms.
