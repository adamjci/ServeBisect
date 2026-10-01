# Contributing to ServeBisect

ServeBisect is most useful when a regression can be rerun by someone who did not discover it. Contributions should therefore optimize for reproducibility and small, reviewable evidence.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

ruff check src tests examples
pytest -q
servebisect demo
```

The test suite must remain runnable without a GPU, cloud account, or model download. Provider-specific tests should use fakes or mocks unless a test is explicitly marked as an external integration check.

## Regression cases

A strong case includes:

- the upstream project and public issue when one exists;
- a known-good revision and a known-bad revision;
- a pinned public model or fixture;
- the required GPU class and count;
- the exact benchmark or semantic check command;
- the regression threshold and direction;
- enough environment information to explain hardware/runtime differences;
- sanitized output that contains no credentials or private prompts.

Prefer a small historical regression with a known answer over a large benchmark that is difficult to reproduce.

## Changes to comparison logic

Metric direction and regression budgets are part of the evidence contract. Changes to them should include a focused test showing both the passing boundary and the failing boundary. Bisection changes should preserve the source checkout and run candidates in detached temporary worktrees.

## Provider changes

Paid GPU allocation needs bounded failure behavior. Provider changes should preserve these properties:

- allocation is explicit;
- a TTL or equivalent provider-side deadline is attached at rent time;
- requested GPU count and price limits are enforced before workload execution;
- failed allocation attempts reconcile any resource that may have been created;
- success and failure paths attempt explicit teardown;
- teardown is verified from fresh provider state;
- credentials never enter reports or committed fixtures.

Do not add live paid-provider calls to the default test suite.

## Pull requests

Keep PRs focused. Describe the concrete failure or workflow being improved, the resulting behavior, and the validation performed. When a change reproduces a public upstream regression, link the upstream issue and include the sanitized ServeBisect artifact when practical.
