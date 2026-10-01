from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .bisect import bisect_metric
from .models import BisectReport, MetricRule


def _run(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def create_demo_repo(root: Path) -> tuple[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    _run(root, "init", "-b", "main")
    _run(root, "config", "user.email", "servebisect@example.invalid")
    _run(root, "config", "user.name", "ServeBisect Demo")
    scores = [100.0, 101.0, 100.5, 100.0, 78.0, 77.5, 77.0]
    revisions: list[str] = []
    for index, score in enumerate(scores):
        payload = {
            "metrics": {"tokens_per_second": score},
            "checks": {"tool_calling": True},
        }
        script = f"import json\nprint(json.dumps({payload!r}))\n"
        (root / "benchmark.py").write_text(script)
        (root / "demo-metadata.json").write_text(
            json.dumps({"revision": index, "expected_tokens_per_second": score}, indent=2) + "\n"
        )
        _run(root, "add", "benchmark.py", "demo-metadata.json")
        _run(root, "commit", "-m", f"demo revision {index}: throughput {score:g}")
        sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        revisions.append(sha)
    return revisions[1], revisions[-1]


def run_demo() -> BisectReport:
    temp = tempfile.TemporaryDirectory(prefix="servebisect-demo-")
    repo = Path(temp.name) / "engine"
    good, bad = create_demo_repo(repo)
    try:
        return bisect_metric(
            repo=repo,
            good=good,
            bad=bad,
            command=[sys.executable, "benchmark.py"],
            rule=MetricRule("tokens_per_second", "higher", 10.0),
            timeout_s=30.0,
        )
    finally:
        temp.cleanup()
