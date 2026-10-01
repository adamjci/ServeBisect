from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .fingerprint import environment_fingerprint
from .models import Observation


class BenchmarkError(RuntimeError):
    pass


def parse_benchmark_payload(stdout: str) -> dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        raise BenchmarkError("benchmark produced no JSON output")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    for line in reversed(stripped.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise BenchmarkError("benchmark output did not contain a JSON object")


def run_benchmark(
    *,
    label: str,
    command: Sequence[str],
    cwd: str | Path | None = None,
    timeout_s: float = 900.0,
    extra_env: Mapping[str, str] | None = None,
    fingerprint: bool = True,
) -> Observation:
    started = time.monotonic()
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BenchmarkError(f"benchmark timed out after {timeout_s:g}s: {command!r}") from exc
    duration = time.monotonic() - started

    if result.returncode != 0:
        raise BenchmarkError(
            f"benchmark exited {result.returncode}: {' '.join(command)}\n{result.stderr.strip()}"
        )
    payload = parse_benchmark_payload(result.stdout)
    metrics_raw = payload.get("metrics", {})
    checks_raw = payload.get("checks", {})
    if not isinstance(metrics_raw, dict) or not isinstance(checks_raw, dict):
        raise BenchmarkError("benchmark JSON fields 'metrics' and 'checks' must be objects")
    metrics = {str(name): float(value) for name, value in metrics_raw.items()}
    checks = {str(name): bool(value) for name, value in checks_raw.items()}
    if not metrics and not checks:
        raise BenchmarkError("benchmark must emit at least one metric or check")

    details = payload.get("details", {})
    if not isinstance(details, dict):
        details = {"value": details}
    return Observation(
        label=label,
        command=list(command),
        returncode=result.returncode,
        duration_s=duration,
        metrics=metrics,
        checks=checks,
        details=details,
        environment=environment_fingerprint() if fingerprint else {},
        stdout=result.stdout,
        stderr=result.stderr,
    )
