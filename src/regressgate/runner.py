"""Run every case `repeats` times against a target and grade each trial.

Repeats are what make noise measurable: one trial per case cannot tell a flaky case from a
broken one. A target exception fails that trial (with the error recorded) instead of the
run; an invalid check config aborts the run, because it would fail every trial for a reason
unrelated to the target.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from regressgate.case_schema import Case
from regressgate.checks import run_checks, validate_cases
from regressgate.run_report import CaseResult, CheckResult, RunReport, Trial
from regressgate.targets import Target

ProgressFn = Callable[[int, int], None]


def run_trial(case: Case, target: Target, keep_output: bool = True) -> Trial:
    started = time.perf_counter()
    try:
        result = target(case.input)
    except Exception as e:
        return Trial(passed=False, latency_s=time.perf_counter() - started,
                     error=f"{type(e).__name__}: {e}")
    latency = time.perf_counter() - started
    outcomes = run_checks(case, result)
    return Trial(
        passed=all(o.passed for o in outcomes.values()),
        checks={k: CheckResult(passed=o.passed, score=o.score, detail=o.detail)
                for k, o in outcomes.items()},
        latency_s=latency,
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        output=result.output if keep_output else None,
    )


def run_suite(
    cases: list[Case],
    target: Target,
    *,
    target_name: str = "",
    repeats: int = 1,
    concurrency: int = 4,
    keep_outputs: bool = True,
    metadata: dict[str, Any] | None = None,
    on_progress: ProgressFn | None = None,
) -> RunReport:
    from regressgate import __version__

    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    validate_cases(cases)
    jobs = [(i, case) for i, case in enumerate(cases) for _ in range(repeats)]
    trials: list[list[Trial]] = [[] for _ in cases]
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [(i, pool.submit(run_trial, case, target, keep_outputs)) for i, case in jobs]
        for i, future in futures:
            trials[i].append(future.result())
            done += 1
            if on_progress:
                on_progress(done, len(jobs))
    return RunReport(
        regressgate_version=__version__,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        target=target_name,
        repeats=repeats,
        metadata=metadata or {},
        cases=[CaseResult(id=c.id, tags=c.tags, trials=t)
               for c, t in zip(cases, trials, strict=True)],
    )
