# Security and cost guardrails

ServeBisect executes third-party inference stacks on expensive accelerators and captures detailed logs. The PoC should therefore make safe execution boundaries visible even before it grows into a larger CI system.

## Credential handling

Provider and service credentials belong outside run plans and reports.

- Read Lium/API tokens from environment variables or an external secret store.
- Never serialize secrets into `plan.json`, provider metadata, command transcripts, fixtures, HTML reports, or issue attachments.
- Redact known secret values from captured stdout/stderr before publishing artifacts.
- Avoid commands that dump the full environment (`env`, `printenv`, broad process dumps) into normal artifacts.
- Use the smallest credential scope the provider supports.
- Treat model-hub tokens, private-repository credentials, and API keys as separate secret classes; a GPU provider credential should not implicitly authorize access to all of them.

ServeBisect should record whether a credential was required for a step, but not the credential itself.

## Remote-code boundary

Testing arbitrary revisions means running code that may be untrusted or simply broken. A clean ephemeral machine reduces contamination between runs, but it does not make remote code harmless.

Recommended defaults:

- do not forward the developer's full local environment;
- transfer only files explicitly required by the run;
- do not mount personal SSH agents or cloud credential directories into the workload;
- prefer disposable provider instances and disposable virtual environments;
- keep host/provider control credentials in the controller where possible instead of exporting them into the remote shell;
- publish logs only after redaction and review when the workload touched private data.

When a regression case requires a private model or repository, the report should indicate that a private dependency existed without copying its token or sensitive contents.

## Command construction

Provider execution APIs ultimately invoke shell commands. ServeBisect should avoid turning user-supplied strings into an unchecked shell program.

Where practical:

- represent commands as argument arrays internally;
- quote/escape at the final provider boundary;
- keep generated bootstrap scripts as artifacts so reviewers can inspect what ran;
- never interpolate secret values into a command string that will be logged;
- validate revision, path, and run-name inputs before embedding them in filenames or remote paths.

## Artifact privacy

Regression artifacts can contain more than benchmark numbers. Raw HTTP traces may include prompts, model outputs, tool arguments, file paths, hostnames, repository URLs, or private error details.

Classify artifacts into two layers:

1. **Private raw evidence** for debugging and exact reproduction.
2. **Publishable report** with volatile identifiers and sensitive content removed or summarized.

The user should choose when a private artifact becomes public. Automated issue/PR integration should upload only the publishable layer unless explicitly configured otherwise.

## Cost model

GPU cost has three relevant parts:

- hourly provider price;
- wall-clock time from allocation through teardown;
- repetition count, including retries and bisect candidates.

A binary search across revisions can multiply the number of GPU runs quickly. A run planner should estimate the upper bound before allocation. For example, a bisect over 64 candidate commits needs at most roughly six classification steps when every step is usable, but retries, warmups, baseline rechecks, and invalid runs can add materially to that number.

For a planned run, record:

```text
max_duration_per_pod
max_hourly_price
max_total_run_cost
max_candidates
max_retries_per_candidate
```

If the provider does not offer a hard spend cap, ServeBisect can still enforce the plan by refusing nodes above the configured price and checking live spend/duration between stages.

## Lium-specific cost controls

For Lium:

```bash
lium ls --format json
lium up <node-id> --count 1 --yes --no-ssh --ttl 45m --name servebisect-<run-id>
lium ps --format json
lium rm <pod>
```

The current wrapper exposes the first cost ceiling directly:

```bash
servebisect lium run \
  --gpu H100 \
  --ttl 45m \
  --max-hourly-price 3.00 \
  --command "nvidia-smi"
```

It filters structured node data, refuses the cheapest eligible node when its quoted hourly price exceeds the ceiling, attaches a TTL to every rent, reconciles a uniquely named pod after a failed rent attempt, explicitly removes the pod after execution, and verifies removal against fresh provider state. A total-run spend ceiling and live spend polling are still future controls.

The account balance can be queried with:

```bash
lium balance --json
```

ServeBisect currently fails before allocation when `--max-hourly-price` cannot be satisfied. A future total-run budget should extend that same fail-before-rent behavior.

## Failure and cleanup policy

Cleanup should run after:

- successful completion;
- engine setup failure;
- provider/transport failure after a pod may have been created;
- check failure;
- timeout;
- user interruption where the runtime can catch the signal.

If cleanup cannot be confirmed, the final result should prominently identify the active provider resource. That condition is operationally more urgent than formatting a finished regression report.

## Public CI defaults

When ServeBisect is eventually used from public pull requests, GPU allocation should be protected from untrusted fork input and spend abuse. Sensible CI policy includes:

- no provider secrets in workflows that run arbitrary fork code;
- an explicit maintainer approval/trusted-label gate before paid GPU allocation;
- repository-defined caps on GPU class, duration, and total candidates;
- immutable recording of the tested commit SHA;
- cancellation cleanup and periodic orphan reconciliation;
- concurrency limits so many PRs cannot exhaust the shared account at once.

These controls are roadmap requirements for a hosted or shared CI deployment. The current PoC should expose the same concepts in its local/provider execution paths without claiming hardened multi-tenant isolation.
