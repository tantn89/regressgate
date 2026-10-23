from __future__ import annotations

from regressgate.run_report import CaseResult, RunReport, Trial


def make_report(
    counts: dict[str, tuple[int, int]], *, latency_s: float = 0.1, cost_usd: float | None = None
) -> RunReport:
    """A report where case `id` passed `passes` of `trials` trials."""
    cases = []
    for case_id, (passes, trials) in counts.items():
        cases.append(CaseResult(id=case_id, trials=[
            Trial(passed=i < passes, latency_s=latency_s, cost_usd=cost_usd)
            for i in range(trials)
        ]))
    repeats = max(t for _, t in counts.values())
    return RunReport(regressgate_version="test", created_at="2026-01-01T00:00:00+00:00",
                     target="test", repeats=repeats, cases=cases)
