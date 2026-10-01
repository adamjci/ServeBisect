from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from servebisect.config import load_run_config
from servebisect.runner import BenchmarkError, run_benchmark


class RunnerAndConfigTests(unittest.TestCase):
    def test_runner_accepts_json_on_last_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "bench.py"
            script.write_text(
                "print('warming up')\n"
                "print('{\"metrics\": {\"throughput\": 12.5}, \"checks\": {\"ok\": true}}')\n"
            )
            result = run_benchmark(
                label="sample",
                command=[sys.executable, str(script)],
                fingerprint=False,
            )
        self.assertEqual(result.metrics["throughput"], 12.5)
        self.assertTrue(result.checks["ok"])

    def test_runner_rejects_non_json(self) -> None:
        with self.assertRaises(BenchmarkError):
            run_benchmark(
                label="bad",
                command=[sys.executable, "-c", "print('nope')"],
                fingerprint=False,
            )

    def test_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "servebisect.toml"
            config.write_text(
                "[baseline]\n"
                "command = ['python', 'a.py']\n"
                "[candidate]\n"
                "command = ['python', 'b.py']\n"
                "[[metrics]]\n"
                "name = 'throughput'\n"
                "direction = 'higher'\n"
                "max_regression_pct = 7\n"
            )
            parsed = load_run_config(config)
        self.assertEqual(parsed.metrics[0].name, "throughput")
        self.assertEqual(parsed.metrics[0].max_regression_pct, 7.0)


if __name__ == "__main__":
    unittest.main()
