from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Direction = Literal["higher", "lower"]


@dataclass(frozen=True)
class MetricRule:
    name: str
    direction: Direction
    max_regression_pct: float = 5.0


@dataclass
class Observation:
    label: str
    command: list[str]
    returncode: int
    duration_s: float
    metrics: dict[str, float] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Observation:
        return cls(
            label=str(value["label"]),
            command=[str(part) for part in value.get("command", [])],
            returncode=int(value.get("returncode", 0)),
            duration_s=float(value.get("duration_s", 0.0)),
            metrics={str(k): float(v) for k, v in value.get("metrics", {}).items()},
            checks={str(k): bool(v) for k, v in value.get("checks", {}).items()},
            details=dict(value.get("details", {})),
            environment=dict(value.get("environment", {})),
            stdout=str(value.get("stdout", "")),
            stderr=str(value.get("stderr", "")),
        )


@dataclass(frozen=True)
class MetricAssessment:
    name: str
    baseline: float
    candidate: float
    direction: Direction
    max_regression_pct: float
    regression_pct: float
    passed: bool


@dataclass(frozen=True)
class CheckAssessment:
    name: str
    baseline: bool | None
    candidate: bool | None
    passed: bool


@dataclass
class ComparisonReport:
    baseline_label: str
    candidate_label: str
    passed: bool
    metrics: list[MetricAssessment]
    checks: list[CheckAssessment]
    baseline: Observation
    candidate: Observation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BisectStep:
    revision: str
    metric_value: float
    regression_pct: float
    passed: bool


@dataclass
class BisectReport:
    repo: str
    good_revision: str
    bad_revision: str
    culprit_revision: str
    culprit_parent: str | None
    metric_rule: MetricRule
    baseline_value: float
    steps: list[BisectStep]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
