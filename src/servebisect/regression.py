from __future__ import annotations

import math

from .models import (
    CheckAssessment,
    ComparisonReport,
    MetricAssessment,
    MetricRule,
    Observation,
)


def regression_pct(baseline: float, candidate: float, direction: str) -> float:
    if baseline == candidate:
        return 0.0
    if baseline == 0:
        return math.inf
    if direction == "higher":
        return max(0.0, (baseline - candidate) / abs(baseline) * 100.0)
    if direction == "lower":
        return max(0.0, (candidate - baseline) / abs(baseline) * 100.0)
    raise ValueError(f"unknown metric direction: {direction}")


def compare_observations(
    baseline: Observation,
    candidate: Observation,
    rules: list[MetricRule],
) -> ComparisonReport:
    metrics: list[MetricAssessment] = []
    for rule in rules:
        if rule.name not in baseline.metrics:
            raise KeyError(f"baseline is missing metric {rule.name!r}")
        if rule.name not in candidate.metrics:
            raise KeyError(f"candidate is missing metric {rule.name!r}")
        base = baseline.metrics[rule.name]
        cand = candidate.metrics[rule.name]
        regression = regression_pct(base, cand, rule.direction)
        metrics.append(
            MetricAssessment(
                name=rule.name,
                baseline=base,
                candidate=cand,
                direction=rule.direction,
                max_regression_pct=rule.max_regression_pct,
                regression_pct=regression,
                passed=regression <= rule.max_regression_pct,
            )
        )

    checks: list[CheckAssessment] = []
    all_check_names = sorted(set(baseline.checks) | set(candidate.checks))
    for name in all_check_names:
        base = baseline.checks.get(name)
        cand = candidate.checks.get(name)
        passed = cand is True and (base is not False)
        checks.append(CheckAssessment(name=name, baseline=base, candidate=cand, passed=passed))

    passed = all(item.passed for item in metrics) and all(item.passed for item in checks)
    return ComparisonReport(
        baseline_label=baseline.label,
        candidate_label=candidate.label,
        passed=passed,
        metrics=metrics,
        checks=checks,
        baseline=baseline,
        candidate=candidate,
    )
