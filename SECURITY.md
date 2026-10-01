# Security

ServeBisect executes third-party inference code and can control paid GPU resources. Treat benchmark revisions, remote command output, and provider credentials as security-sensitive inputs.

## Reporting a vulnerability

Do not publish credentials, private prompts, exploit details, or other sensitive material in a public issue. Until this repository publishes a dedicated private security contact, open a minimal public issue that contains no sensitive details and asks the maintainers for a private reporting channel.

For non-sensitive hardening bugs, normal issues and pull requests are appropriate.

## Supported versions

ServeBisect is currently an alpha PoC. Security fixes are applied to the latest development version; there is not yet a maintained multi-version support window.

## Operational boundary

ServeBisect is not a sandbox. A benchmark command or checked-out revision can execute arbitrary code with the permissions of the environment in which it runs. Use disposable environments for untrusted revisions, forward only the credentials the workload actually needs, and review artifacts before publishing them.

The Lium integration uses TTL-backed ephemeral resources and explicit verified teardown, but controller crashes can still interrupt local cleanup. Provider-side TTL is the final backstop until orphan reconciliation is implemented.
