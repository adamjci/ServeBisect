from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from servebisect.bisect import bisect_metric
from servebisect.demo import create_demo_repo
from servebisect.models import MetricRule


class BisectTests(unittest.TestCase):
    def test_finds_first_bad_revision_without_moving_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            good, bad = create_demo_repo(repo)
            source_head_before = (repo / ".git" / "HEAD").read_text()
            report = bisect_metric(
                repo=repo,
                good=good,
                bad=bad,
                command=["python3", "benchmark.py"],
                rule=MetricRule("tokens_per_second", "higher", 10.0),
                timeout_s=30.0,
            )
            source_head_after = (repo / ".git" / "HEAD").read_text()

        self.assertEqual(source_head_before, source_head_after)
        self.assertNotEqual(report.culprit_revision, good)
        bad_steps = [step for step in report.steps if not step.passed]
        self.assertTrue(bad_steps)
        culprit_step = next(step for step in report.steps if step.revision == report.culprit_revision)
        self.assertFalse(culprit_step.passed)


if __name__ == "__main__":
    unittest.main()
