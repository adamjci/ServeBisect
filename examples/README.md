# Examples

Examples should be small, public, and rerunnable. Their job is to demonstrate the ServeBisect workflow without requiring a maintainer to reverse-engineer a large benchmark environment.

## Included example

The repository ships an offline comparison that requires no GPU, provider account, or model download:

```bash
servebisect run examples/servebisect.toml
```

`examples/servebisect.toml` runs `baseline.py` and `candidate.py`. Each script prints the benchmark JSON contract used by ServeBisect:

```json
{
  "metrics": {
    "tokens_per_second": 100.0,
    "ttft_ms": 80.0
  },
  "checks": {
    "tool_calling": true,
    "structured_output": true
  }
}
```

The candidate deliberately lowers `tokens_per_second` from `100` to `91`, while the config allows only a 5% regression. The command therefore writes `examples/servebisect-report.json` and `examples/servebisect-report.md`, prints a `REGRESSION` summary, and exits with status `1`. That non-zero status is expected for this fixture and demonstrates the CI gate.

For a deterministic git-bisect exercise that creates and removes its own temporary repository, run:

```bash
servebisect demo \
  --json /tmp/servebisect-demo.json \
  --markdown /tmp/servebisect-demo.md
```

An example regression case should identify:

```text
project / engine
known-good revision
known-bad revision
model + pinned revision where practical
workload / conformance suite
expected signal and threshold
required hardware
expected runtime / rough cost envelope
```

## Local-first examples

Keep at least one fixture that runs with no GPU and no provider credentials. The included baseline/candidate fixture currently demonstrates:

- baseline vs candidate execution;
- structured result capture;
- boolean semantic/check comparison;
- report generation;
- distinct success/regression exit status, with harness/setup errors surfaced separately.

This fixture is useful for development and CI because provider availability never becomes a prerequisite for testing ServeBisect itself.

## GPU case studies

For a real GPU regression, prefer a historical public issue whose expected good/bad boundary is already known. A case directory can keep the user-facing material compact:

```text
examples/<case>/
├── README.md
├── case.json        # or another stable ServeBisect run-plan format
├── expected.json    # expected classification / known first-bad range
└── artifacts/       # sanitized small artifacts, when useful
```

Do not commit large model weights, provider credentials, access tokens, or raw private prompts into an example.

## Provider lifecycle in examples

Any example that allocates a Lium GPU should make the bounded lifecycle obvious:

```bash
lium ls --format json
lium up <node-id> --count 1 --yes --no-ssh --ttl 45m --name servebisect-example
lium exec <pod> --json "<workload-command>"
lium rm <pod>
lium ps --format json
```

The final listing is part of the example because it verifies that teardown completed. A demo should never rely on TTL alone to end billing.

## Publishing a case

Before adding a regression case to the public repository:

1. rerun it from a clean environment;
2. confirm the stated good/bad result is reproducible;
3. pin versions closely enough to avoid accidental drift;
4. sanitize logs and HTTP traces;
5. record hardware/runtime assumptions;
6. link the original public issue or upstream discussion when one exists;
7. distinguish measured results from hypotheses about root cause.

The strongest ServeBisect examples should be useful upstream even for maintainers who never use Lium or the same GPU provider.
