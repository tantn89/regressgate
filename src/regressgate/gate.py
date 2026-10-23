"""Compare a head run against a base run and decide: pass, improvement, warn or regression.

A regression needs a practically relevant size (a mean pass-rate drop larger than
`margin`) and statistical evidence from either of two tests, each run at alpha / 2 so the
overall false-alarm rate stays at or below `alpha`:

- the aggregate test: a stratified permutation test on the mean per-case difference, which
  catches broad, moderate degradation;
- the per-case test: one-sided Fisher exact tests with Tarone's correction, which catch a
  single case that broke even when flaky cases add noise to the aggregate.

A drop without evidence is a `warn`: visible in the report, not a red build. Budgets and a
pass-rate floor are hard limits that fail regardless of statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from regressgate.gate_statistics import (
    CaseCounts,
    fisher_worse,
    min_achievable_p,
    permutation_test,
    tarone_threshold,
)
from regressgate.run_report import CaseResult, RunReport

Verdict = Literal["pass", "improvement", "warn", "regression"]


class GateConfig(BaseModel):
    alpha: float = Field(0.05, gt=0, lt=1)
    margin: float = Field(0.0, ge=0, le=1)  # smallest pass-rate drop (0-1) that matters
    permutations: int = Field(10_000, ge=100)
    seed: int = 0
    min_pass_rate: float | None = Field(None, ge=0, le=1)
    max_mean_cost_usd: float | None = Field(None, ge=0)
    max_p95_latency_s: float | None = Field(None, ge=0)
    fail_on: Literal["regression", "warn"] = "regression"


@dataclass(frozen=True)
class CaseChange:
    id: str
    base: CaseCounts
    head: CaseCounts
    p_worse: float
    significant: bool  # below the per-case (Tarone) threshold

    @property
    def delta(self) -> float:
        return self.head.rate - self.base.rate


@dataclass
class GateResult:
    verdict: Verdict
    failed: bool
    base_rate: float
    head_rate: float
    delta: float
    p_worse: float
    p_better: float
    case_threshold: float  # per-case p-value threshold after Tarone's correction
    permutations: int
    cases_compared: int
    base_repeats: int
    head_repeats: int
    changes: list[CaseChange] = field(default_factory=list)  # cases whose rate moved, worst first
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    limit_failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _counts(case: CaseResult) -> CaseCounts:
    return CaseCounts(case.passes, len(case.trials))


def compare_reports(
    base: RunReport, head: RunReport, config: GateConfig | None = None
) -> GateResult:
    config = config or GateConfig()
    base_by_id = {c.id: c for c in base.cases}
    head_by_id = {c.id: c for c in head.cases}
    shared = [cid for cid in base_by_id if cid in head_by_id]
    if not shared:
        raise ValueError("base and head reports share no case ids")
    base_counts = [_counts(base_by_id[cid]) for cid in shared]
    head_counts = [_counts(head_by_id[cid]) for cid in shared]
    half_alpha = config.alpha / 2
    test = permutation_test(base_counts, head_counts,
                            permutations=config.permutations, seed=config.seed)
    pairs = list(zip(shared, base_counts, head_counts, strict=True))
    threshold = tarone_threshold([min_achievable_p(b, h) for _, b, h in pairs], half_alpha)
    changes = []
    for cid, b, h in pairs:
        if b.rate != h.rate:
            p = fisher_worse(b, h)
            changes.append(CaseChange(cid, b, h, p,
                                      significant=h.rate < b.rate and p <= threshold))
    changes.sort(key=lambda c: (c.delta, c.p_worse))
    limits = _limit_failures(head, config)
    notes = []
    if min(base.repeats, head.repeats) < 3:
        notes.append("Fewer than 3 trials per case: noise cannot be separated from real "
                     "change, so only large, consistent drops can reach significance. "
                     "Run with --repeats 3 or more.")

    evidence = test.p_worse < half_alpha or any(c.significant for c in changes)
    if (test.delta < -config.margin and evidence) or limits:
        verdict: Verdict = "regression"
    elif test.delta < -config.margin:
        verdict = "warn"
        notes.append(f"The drop is within noise (aggregate p = {test.p_worse:.3f}, no case "
                     f"below {threshold:.4f}); re-run with more repeats to confirm or clear it.")
    elif test.delta > config.margin and test.p_better < half_alpha:
        verdict = "improvement"
    else:
        verdict = "pass"

    return GateResult(
        verdict=verdict,
        failed=verdict == "regression" or (config.fail_on == "warn" and verdict == "warn"),
        base_rate=sum(c.rate for c in base_counts) / len(shared),
        head_rate=sum(c.rate for c in head_counts) / len(shared),
        delta=test.delta,
        p_worse=test.p_worse,
        p_better=test.p_better,
        case_threshold=threshold,
        permutations=test.permutations,
        cases_compared=len(shared),
        base_repeats=base.repeats,
        head_repeats=head.repeats,
        changes=changes,
        added=[cid for cid in head_by_id if cid not in base_by_id],
        removed=[cid for cid in base_by_id if cid not in head_by_id],
        limit_failures=limits,
        notes=notes,
    )


def _limit_failures(head: RunReport, config: GateConfig) -> list[str]:
    failures = []
    if config.min_pass_rate is not None and head.pass_rate < config.min_pass_rate:
        failures.append(f"pass rate {head.pass_rate:.1%} is below the floor "
                        f"{config.min_pass_rate:.1%}")
    cost = head.mean_cost_usd()
    budget = config.max_mean_cost_usd
    if budget is not None and cost is not None and cost > budget:
        failures.append(f"mean cost ${cost:.4f} per trial exceeds ${budget:.4f}")
    p95 = head.latency_quantile(0.95)
    if config.max_p95_latency_s is not None and p95 > config.max_p95_latency_s:
        failures.append(f"p95 latency {p95:.2f}s exceeds {config.max_p95_latency_s:.2f}s")
    return failures
