from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import BisectReport, BisectStep, MetricRule
from .regression import regression_pct
from .runner import run_benchmark


class BisectError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BisectError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _revisions(repo: Path, good: str, bad: str) -> list[str]:
    good_sha = _git(repo, "rev-parse", good)
    bad_sha = _git(repo, "rev-parse", bad)
    ancestry = _git(repo, "merge-base", "--is-ancestor", good_sha, bad_sha)
    del ancestry
    commits = _git(repo, "rev-list", "--ancestry-path", "--reverse", f"{good_sha}..{bad_sha}")
    revisions = [line for line in commits.splitlines() if line]
    if not revisions or revisions[-1] != bad_sha:
        raise BisectError("bad revision is not reachable from good revision")
    return [good_sha, *revisions]


def _run_at_revision(
    repo: Path,
    revision: str,
    command: list[str],
    *,
    timeout_s: float,
) -> dict[str, float]:
    worktree_root = Path(tempfile.mkdtemp(prefix="servebisect-bisect-"))
    worktree = worktree_root / "checkout"
    try:
        _git(repo, "worktree", "add", "--detach", str(worktree), revision)
        observation = run_benchmark(
            label=revision[:12],
            command=command,
            cwd=worktree,
            timeout_s=timeout_s,
            fingerprint=False,
        )
        return observation.metrics
    finally:
        if worktree.exists():
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
                check=False,
            )
        shutil.rmtree(worktree_root, ignore_errors=True)


def bisect_metric(
    *,
    repo: str | Path,
    good: str,
    bad: str,
    command: list[str],
    rule: MetricRule,
    timeout_s: float = 900.0,
) -> BisectReport:
    repo_path = Path(repo).resolve()
    revisions = _revisions(repo_path, good, bad)
    baseline_metrics = _run_at_revision(repo_path, revisions[0], command, timeout_s=timeout_s)
    if rule.name not in baseline_metrics:
        raise BisectError(f"benchmark does not emit metric {rule.name!r} at good revision")
    baseline_value = baseline_metrics[rule.name]
    cache: dict[str, BisectStep] = {}

    def assess(revision: str) -> BisectStep:
        if revision in cache:
            return cache[revision]
        metrics = _run_at_revision(repo_path, revision, command, timeout_s=timeout_s)
        if rule.name not in metrics:
            raise BisectError(f"benchmark does not emit metric {rule.name!r} at {revision[:12]}")
        value = metrics[rule.name]
        regression = regression_pct(baseline_value, value, rule.direction)
        step = BisectStep(
            revision=revision,
            metric_value=value,
            regression_pct=regression,
            passed=regression <= rule.max_regression_pct,
        )
        cache[revision] = step
        return step

    cache[revisions[0]] = BisectStep(
        revision=revisions[0], metric_value=baseline_value, regression_pct=0.0, passed=True
    )
    if assess(revisions[-1]).passed:
        raise BisectError("bad revision does not exceed the configured regression budget")

    lo = 0
    hi = len(revisions) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if assess(revisions[mid]).passed:
            lo = mid
        else:
            hi = mid

    culprit = revisions[hi]
    return BisectReport(
        repo=str(repo_path),
        good_revision=revisions[0],
        bad_revision=revisions[-1],
        culprit_revision=culprit,
        culprit_parent=revisions[hi - 1] if hi > 0 else None,
        metric_rule=rule,
        baseline_value=baseline_value,
        steps=list(cache.values()),
    )
