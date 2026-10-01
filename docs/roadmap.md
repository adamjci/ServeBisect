# Roadmap

ServeBisect should earn scope by proving that it can reproduce real regressions reliably. The roadmap is therefore organized around increasingly reusable evidence rather than provider count or feature count alone.

## Milestone 0: local PoC

Goal: run the complete comparison loop on a normal development machine without cloud credentials.

Status: substantially implemented in the current PoC. The config-driven runner, JSON/Markdown reports, environment fingerprinting, semantic booleans, endpoint conformance probes, streaming endpoint benchmark, and deterministic demo are present. More robust failure classification and statistical measurement remain.

Acceptance criteria:

- a CLI can describe and execute a baseline/candidate comparison;
- the run captures environment metadata and raw logs;
- at least one performance check and one semantic/conformance check return structured results;
- comparison produces a stable JSON artifact;
- infrastructure/setup failures are distinguishable from regressions;
- tests run without requiring a GPU or network account.

This milestone makes every later provider integration testable offline.

## Milestone 1: ephemeral GPU reproduction

Goal: reproduce the same run on a clean Lium GPU with bounded cost.

Status: lifecycle foundation implemented. Current code checks for Lium CLI `>=0.0.42`, uses structured discovery, supports `--max-hourly-price`, rents with TTL/non-interactive flags, executes through `lium exec --json`, reconciles a named pod after failed rent, removes in cleanup, and verifies removal. End-to-end run/report integration and total-run spend accounting remain.

Acceptance criteria:

- node discovery uses `lium ls --format json`;
- every rent is non-interactive and includes `--yes --no-ssh --ttl`;
- command execution captures `lium exec --json` results;
- failed startup paths reconcile provider state before returning;
- success, failure, timeout, and interruption paths attempt explicit `lium rm`;
- teardown is verified with fresh provider state;
- reports include provider/GPU identity and non-secret cost metadata.

## Milestone 2: useful engine adapters

Goal: reproduce real issues in vLLM and SGLang with consistent engine lifecycle handling.

Acceptance criteria:

- pinned install/build of selected source/package revisions;
- consistent server startup and health checks;
- captured engine config/version/logs;
- common workload definition usable across both engines where their APIs overlap;
- at least one published historical regression case per engine.

## Milestone 3: semantic conformance suite

Goal: catch API regressions that a throughput benchmark cannot see.

Status: first four probes are implemented (`basic_chat`, `json_object`, `tool_choice`, `stream_sse`). The stricter cases below remain roadmap work.

Initial coverage:

- basic chat-completion response shape;
- streaming events and finish behavior;
- structured JSON/schema-constrained output;
- tool calls and parallel tool-call representation;
- deterministic comparison after normalization of volatile fields;
- error and cancellation behavior where a portable expectation exists.

Acceptance criteria:

- every failed assertion preserves the raw request/response evidence;
- normalizers are explicit and testable;
- engine-specific extensions are separated from portable OpenAI-compatible expectations.

## Milestone 4: bisection

Goal: reduce a known-good/known-bad range to the smallest useful culprit range.

Status: metric-based commit bisection is implemented with detached temporary worktrees and a synthetic deterministic demo. Package-version enumeration, invalid-run retries, persistence/resume, and noise-aware repeated classification remain.

Acceptance criteria:

- commit/revision candidate enumeration;
- package-version candidate enumeration;
- bounded retries for invalid infrastructure runs;
- stable pass/regression/invalid classification;
- persistent record of every candidate tested;
- resume support so a long bisect does not discard completed GPU work.

For noisy performance regressions, classification should eventually support repeated samples and confidence-aware policies instead of assuming one measurement is decisive.

## Milestone 5: maintainer-ready reports and CI

Goal: make the output easy to attach to an upstream issue or consume from CI.

Status: JSON/Markdown comparison reports, local CI, and a Lium same-pod comparison path are implemented. The Lium comparison records provider/GPU identity and hourly price. HTML output, total provider spend, artifact upload, trusted paid-CI gates, and orphan reconciliation remain.

Acceptance criteria:

- JSON remains the stable source artifact;
- a readable HTML or Markdown report summarizes the regression and environment;
- reproduction commands are copyable and free of credentials;
- GitHub Action integration can upload sanitized artifacts;
- public-fork workflows require an explicit trusted gate before paid GPU allocation;
- cancellation/orphan reconciliation prevents forgotten GPU resources.

## Milestone 6: public regression corpus

Goal: turn isolated runs into a reusable OSS dataset.

Status: the first case definition, `cases/vllm-49013`, is checked in with an independently documented vLLM good/bad boundary and a root-cause CUDA microbenchmark. A successful live GPU artifact is still required before counting it as a reproduced case.

A useful case record should contain:

- upstream project/issue reference;
- good and bad revisions;
- model/workload and required GPU class;
- expected failure signal;
- sanitized ServeBisect report;
- whether the case still reproduces on current provider images/drivers.

The corpus should favor a small number of high-quality, rerunnable cases over a large list of unverified issue links.

## Later directions

Once the execution and artifact contracts are stable, possible extensions include:

- more GPU providers;
- AMD/ROCm and additional accelerator backends;
- multi-GPU and multi-node regressions;
- trace replay and production-shaped workloads;
- memory/OOM regression checks;
- automatic issue ingestion and candidate-range generation;
- optional code-analysis assistance for suspect commits and regression-test drafting;
- scheduled qualification matrices across engine releases and GPU families.

These are roadmap directions, not statements of current support.

## Project evidence

The project should describe achieved results separately from planned work. Useful evidence includes:

- public releases and reproducible tags;
- historical regressions reproduced from scratch;
- upstream issues or PRs that reference ServeBisect artifacts;
- external users rerunning cases;
- CI runs using the tool repeatedly;
- measured GPU hours/cost associated with public case studies;
- maintainer workload reduced by a concrete reproduction or narrowed culprit range.
