from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import MetricRule


@dataclass(frozen=True)
class RunTarget:
    label: str
    command: list[str]
    cwd: str | None = None
    timeout_s: float = 900.0


@dataclass(frozen=True)
class RunConfig:
    baseline: RunTarget
    candidate: RunTarget
    metrics: list[MetricRule]
    json_report: str = "servebisect-report.json"
    markdown_report: str = "servebisect-report.md"


def _target(data: dict[str, Any], fallback_label: str) -> RunTarget:
    command = data.get("command")
    if not isinstance(command, list) or not command:
        raise ValueError(f"{fallback_label}.command must be a non-empty TOML array")
    return RunTarget(
        label=str(data.get("label", fallback_label)),
        command=[str(part) for part in command],
        cwd=str(data["cwd"]) if data.get("cwd") else None,
        timeout_s=float(data.get("timeout_s", 900.0)),
    )


def load_run_config(path: str | Path) -> RunConfig:
    config_path = Path(path)
    raw = tomllib.loads(config_path.read_text())
    baseline = _target(dict(raw.get("baseline", {})), "baseline")
    candidate = _target(dict(raw.get("candidate", {})), "candidate")
    metrics_raw = raw.get("metrics", [])
    if not isinstance(metrics_raw, list) or not metrics_raw:
        raise ValueError("config must define at least one [[metrics]] rule")
    metrics = [
        MetricRule(
            name=str(item["name"]),
            direction=str(item.get("direction", "higher")),  # type: ignore[arg-type]
            max_regression_pct=float(item.get("max_regression_pct", 5.0)),
        )
        for item in metrics_raw
    ]
    for metric in metrics:
        if metric.direction not in {"higher", "lower"}:
            raise ValueError(f"metric {metric.name!r} has invalid direction {metric.direction!r}")
    output = dict(raw.get("output", {}))
    return RunConfig(
        baseline=baseline,
        candidate=candidate,
        metrics=metrics,
        json_report=str(output.get("json", "servebisect-report.json")),
        markdown_report=str(output.get("markdown", "servebisect-report.md")),
    )
