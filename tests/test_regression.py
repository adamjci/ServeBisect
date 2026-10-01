from __future__ import annotations

import unittest

from servebisect.models import MetricRule, Observation
from servebisect.regression import compare_observations, regression_pct


def observation(label: str, *, throughput: float, ttft: float, checks: dict[str, bool]) -> Observation:
    return Observation(
        label=label,
        command=["benchmark"],
        returncode=0,
        duration_s=1.0,
        metrics={"throughput": throughput, "ttft_ms": ttft},
        checks=checks,
    )


class RegressionTests(unittest.TestCase):
    def test_higher_is_better_regression(self) -> None:
        self.assertAlmostEqual(regression_pct(100.0, 90.0, "higher"), 10.0)
        self.assertEqual(regression_pct(100.0, 110.0, "higher"), 0.0)

    def test_lower_is_better_regression(self) -> None:
        self.assertAlmostEqual(regression_pct(80.0, 88.0, "lower"), 10.0)
        self.assertEqual(regression_pct(80.0, 70.0, "lower"), 0.0)

    def test_compare_catches_metric_and_semantic_regressions(self) -> None:
        baseline = observation(
            "base", throughput=100.0, ttft=80.0, checks={"tools": True, "json": True}
        )
        candidate = observation(
            "candidate", throughput=92.0, ttft=84.0, checks={"tools": False, "json": True}
        )
        report = compare_observations(
            baseline,
            candidate,
            [
                MetricRule("throughput", "higher", 5.0),
                MetricRule("ttft_ms", "lower", 10.0),
            ],
        )
        self.assertFalse(report.passed)
        by_metric = {item.name: item for item in report.metrics}
        self.assertFalse(by_metric["throughput"].passed)
        self.assertTrue(by_metric["ttft_ms"].passed)
        by_check = {item.name: item for item in report.checks}
        self.assertFalse(by_check["tools"].passed)


if __name__ == "__main__":
    unittest.main()
