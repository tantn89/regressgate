"""Markdown for terminals, GitHub step summaries and PR comments."""

from __future__ import annotations

from regressgate.gate import GateResult
from regressgate.gate_statistics import CaseCounts, rerun_interval
from regressgate.run_report import RunReport

# Marker so the GitHub Action can find and update its own PR comment.
COMMENT_MARKER = "<!-- regressgate -->"
_MAX_ROWS = 15


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _pp(value: float) -> str:
    return f"{100 * value:+.1f} pp"


def _counts(c: CaseCounts) -> str:
    return f"{c.passes}/{c.trials}"


def render_run(report: RunReport, *, seed: int = 0) -> str:
    counts = [CaseCounts(c.passes, len(c.trials)) for c in report.cases]
    interval = rerun_interval(counts, seed=seed)
    spread = (f" (re-run range {_pct(interval.low)} to {_pct(interval.high)})"
              if interval else "")
    cost = report.mean_cost_usd()
    flaky = [c.id for c in report.cases if c.flaky]
    lines = [
        f"### regressgate run: {_pct(report.pass_rate)} pass rate{spread}",
        "",
        "| Cases | Trials per case | Flaky cases | p50 latency | p95 latency | Mean cost |",
        "|---|---|---|---|---|---|",
        f"| {len(report.cases)} | {report.repeats} | {len(flaky)} | "
        f"{report.latency_quantile(0.5):.2f}s | {report.latency_quantile(0.95):.2f}s | "
        f"{'n/a' if cost is None else f'${cost:.4f}'} |",
        "",
        "| Check | Pass rate | Mean score |",
        "|---|---|---|",
    ]
    scores = report.mean_scores()
    for name, rate in report.check_pass_rates().items():
        score = f"{scores[name]:.3f}" if name in scores else ""
        lines.append(f"| `{name}` | {_pct(rate)} | {score} |")
    failing = [c for c in report.cases if c.pass_rate < 1]
    if failing:
        lines += ["", "| Failing case | Passed | Why (first failed trial) |", "|---|---|---|"]
        for case in sorted(failing, key=lambda c: c.pass_rate)[:_MAX_ROWS]:
            trial = next(t for t in case.trials if not t.passed)
            why = trial.error or "; ".join(
                f"{k}: {v.detail}" for k, v in trial.checks.items() if not v.passed)
            lines.append(f"| `{case.id}` | {case.passes}/{len(case.trials)} | "
                         f"{why.replace('|', '/')[:160]} |")
    return "\n".join(lines)


def render_gate(result: GateResult) -> str:
    headline = {
        "regression": "REGRESSION",
        "warn": "WARN: possible regression, not significant",
        "improvement": "IMPROVEMENT",
        "pass": "PASS",
    }[result.verdict]
    lines = [
        COMMENT_MARKER,
        f"## regressgate: {headline}",
        "",
        f"Pass rate **{_pct(result.base_rate)} -> {_pct(result.head_rate)}** "
        f"({_pp(result.delta)}) over {result.cases_compared} shared cases, "
        f"{result.base_repeats} vs {result.head_repeats} trials per case. "
        f"Aggregate permutation p-value for a drop: **{result.p_worse:.4f}** "
        f"({result.permutations:,} shuffles); per-case threshold "
        f"{result.case_threshold:.4f} (Fisher exact, Tarone-corrected).",
    ]
    if result.limit_failures:
        lines += ["", "**Limits exceeded**", *[f"- {f}" for f in result.limit_failures]]
    if result.changes:
        lines += ["", "| Case | Base | Head | Change | Fisher p (worse) | Significant |",
                  "|---|---|---|---|---|---|"]
        for c in result.changes[:_MAX_ROWS]:
            mark = "yes" if c.significant else ""
            lines.append(f"| `{c.id}` | {_counts(c.base)} | {_counts(c.head)} | {_pp(c.delta)} | "
                         f"{c.p_worse:.4f} | {mark} |")
        if len(result.changes) > _MAX_ROWS:
            lines.append(f"| ... {len(result.changes) - _MAX_ROWS} more | | | | | |")
    if result.added or result.removed:
        lines += ["", f"Not compared: {len(result.added)} new case(s), "
                      f"{len(result.removed)} removed case(s)."]
    if result.notes:
        lines += ["", *[f"> {n}" for n in result.notes]]
    return "\n".join(lines)
