"""The JSON report of one suite run: every trial of every case, with check outcomes and cost.

Reports are the unit of comparison: `regressgate compare base.json head.json`. The schema is
versioned so a report written by one release can be read (or rejected clearly) by another.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class CheckResult(BaseModel):
    passed: bool
    score: float | None = None
    detail: str = ""


class Trial(BaseModel):
    passed: bool
    checks: dict[str, CheckResult] = Field(default_factory=dict)
    latency_s: float
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    output: str | None = None


class CaseResult(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    trials: list[Trial]

    @property
    def passes(self) -> int:
        return sum(t.passed for t in self.trials)

    @property
    def pass_rate(self) -> float:
        return self.passes / len(self.trials)

    @property
    def flaky(self) -> bool:
        """Both outcomes observed across trials of the same input."""
        return 0 < self.passes < len(self.trials)


class RunReport(BaseModel):
    schema_version: int = SCHEMA_VERSION
    regressgate_version: str
    created_at: str
    target: str
    repeats: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    cases: list[CaseResult]

    @property
    def trials(self) -> list[Trial]:
        return [t for c in self.cases for t in c.trials]

    @property
    def pass_rate(self) -> float:
        """Mean of per-case pass rates: every case weighs the same, whatever its repeats."""
        return statistics.fmean(c.pass_rate for c in self.cases)

    def check_pass_rates(self) -> dict[str, float]:
        totals: dict[str, list[bool]] = {}
        for trial in self.trials:
            for label, outcome in trial.checks.items():
                totals.setdefault(label.split("#")[0], []).append(outcome.passed)
        return {k: sum(v) / len(v) for k, v in sorted(totals.items())}

    def mean_scores(self) -> dict[str, float]:
        totals: dict[str, list[float]] = {}
        for trial in self.trials:
            for label, outcome in trial.checks.items():
                if outcome.score is not None:
                    totals.setdefault(label.split("#")[0], []).append(outcome.score)
        return {k: statistics.fmean(v) for k, v in sorted(totals.items())}

    def latency_quantile(self, q: float) -> float:
        values = sorted(t.latency_s for t in self.trials)
        return values[min(len(values) - 1, round(q * (len(values) - 1)))]

    def mean_cost_usd(self) -> float | None:
        costs = [t.cost_usd for t in self.trials if t.cost_usd is not None]
        return statistics.fmean(costs) if costs else None

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # LF on every OS, so a committed baseline does not churn between machines.
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
        return path

    @classmethod
    def load(cls, path: str | Path) -> RunReport:
        report = cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
        if report.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"{path}: report schema v{report.schema_version}, this regressgate reads "
                f"v{SCHEMA_VERSION}; re-run the suite to regenerate it"
            )
        return report
