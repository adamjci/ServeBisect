from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servebisect.cli import main
from servebisect.providers.lium import LiumCLI, LiumNode, LiumRunResult


class CLITests(unittest.TestCase):
    @patch.object(LiumCLI, "run_ephemeral_commands")
    def test_lium_compare_writes_regression_report(self, run_commands) -> None:
        node = LiumNode("node-1", "A100", 8, 0.3, 0.3, "US", 80.0)
        run_commands.return_value = [
            LiumRunResult(
                "pod-1",
                node,
                0,
                json.dumps(
                    {
                        "metrics": {"staging_steps_per_second": 100.0},
                        "checks": {"cuda_available": True},
                        "details": {"variant": "parent"},
                    }
                ),
                "",
                1,
            ),
            LiumRunResult(
                "pod-1",
                node,
                0,
                json.dumps(
                    {
                        "metrics": {"staging_steps_per_second": 50.0},
                        "checks": {"cuda_available": True},
                        "details": {"variant": "culprit"},
                    }
                ),
                "",
                1,
            ),
        ]
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "report.json"
            markdown = Path(temp) / "report.md"
            status = main(
                [
                    "lium",
                    "compare",
                    "--gpu",
                    "A100",
                    "--baseline-command",
                    "python good.py",
                    "--candidate-command",
                    "python bad.py",
                    "--metric",
                    "staging_steps_per_second",
                    "--max-regression-pct",
                    "20",
                    "--json",
                    str(report),
                    "--markdown",
                    str(markdown),
                ]
            )
            payload = json.loads(report.read_text())
            rendered = markdown.read_text()
        self.assertEqual(status, 1)
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["baseline"]["environment"]["gpu_type"], "A100")
        self.assertEqual(payload["baseline"]["environment"]["gpu_count"], 1)
        self.assertIn("REGRESSION", rendered)


if __name__ == "__main__":
    unittest.main()
