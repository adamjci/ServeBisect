from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .models import BisectReport, ComparisonReport


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def write_json_report(report: ComparisonReport | BisectReport | dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n")


def comparison_markdown(report: ComparisonReport) -> str:
    status = "PASS" if report.passed else "REGRESSION"
    lines = [
        f"# ServeBisect report — {status}",
        "",
        f"Baseline: `{report.baseline_label}`  ",
        f"Candidate: `{report.candidate_label}`",
        "",
        "## Metrics",
        "",
        "| Metric | Baseline | Candidate | Direction | Regression | Budget | Result |",
        "| --- | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for metric in report.metrics:
        regression = "∞" if metric.regression_pct == float("inf") else f"{metric.regression_pct:.2f}%"
        lines.append(
            f"| {metric.name} | {metric.baseline:g} | {metric.candidate:g} | {metric.direction} "
            f"| {regression} | {metric.max_regression_pct:g}% | "
            f"{'✅' if metric.passed else '❌'} |"
        )
    if report.checks:
        lines.extend(
            [
                "",
                "## Semantic checks",
                "",
                "| Check | Baseline | Candidate | Result |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in report.checks:
            lines.append(
                f"| {check.name} | {check.baseline} | {check.candidate} | "
                f"{'✅' if check.passed else '❌'} |"
            )
    return "\n".join(lines) + "\n"


def bisect_markdown(report: BisectReport) -> str:
    lines = [
        "# ServeBisect bisect report",
        "",
        f"First bad revision: `{report.culprit_revision}`",
        f"Last known good parent: `{report.culprit_parent or 'unknown'}`",
        f"Metric: `{report.metric_rule.name}` ({report.metric_rule.direction} is better)",
        f"Regression budget: `{report.metric_rule.max_regression_pct:g}%`",
        "",
        "| Revision | Value | Regression | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for step in report.steps:
        lines.append(
            f"| `{step.revision[:12]}` | {step.metric_value:g} | {step.regression_pct:.2f}% | "
            f"{'good' if step.passed else 'bad'} |"
        )
    return "\n".join(lines) + "\n"


def write_markdown(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
