"""How often does each gate fail CI when nothing changed, and when something did?

Simulates a 20-case eval suite with realistic LLM noise (most cases stable, a few flaky),
draws base and head runs from known per-case pass probabilities, and applies three gates:

- naive:        fail when the head pass rate is lower than the base pass rate at all;
- tolerance:    fail when it is lower by more than 5 percentage points;
- regressgate:  `compare_reports` with default settings (alpha 0.05).

    python benchmarks/false_alarm_simulation.py [--sims 400] [--out benchmarks/results.md]
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from regressgate.gate import GateConfig, compare_reports
from regressgate.run_report import CaseResult, RunReport, Trial

# True pass probabilities: 12 stable cases, 4 nearly stable, 4 flaky.
BASE_P = [1.0] * 12 + [0.95] * 4 + [0.8, 0.7, 0.6, 0.5]


def _broken_case(p: list[float]) -> list[float]:
    return [0.0, *p[1:]]  # one stable case now always fails


def _broad_drop(p: list[float]) -> list[float]:
    return [min(x, 0.85) if i < 12 else x for i, x in enumerate(p)]  # stable cases now 85%


SCENARIOS: dict[str, Callable[[list[float]], list[float]]] = {
    "no change": lambda p: list(p),
    "one stable case breaks (-5 pp)": _broken_case,
    "stable cases drop to 85% (-9 pp)": _broad_drop,
}
REPEATS = (1, 3, 5, 10)
TOLERANCE = 0.05
GATE = GateConfig(permutations=2000)


def _report(probs: list[float], repeats: int, rng: random.Random) -> RunReport:
    cases = [
        CaseResult(id=f"case-{i}", trials=[
            Trial(passed=rng.random() < p, latency_s=0.0) for _ in range(repeats)])
        for i, p in enumerate(probs)
    ]
    return RunReport(regressgate_version="sim", created_at="", target="sim",
                     repeats=repeats, cases=cases)


SimResult = tuple[str, int, list[bool], list[bool], list[bool]]


def _simulate(args: tuple[str, int, int, int]) -> SimResult:
    scenario, repeats, sims, seed = args
    rng = random.Random(seed)
    head_p = SCENARIOS[scenario](BASE_P)
    naive, tolerance, gated = [], [], []
    for i in range(sims):
        base, head = _report(BASE_P, repeats, rng), _report(head_p, repeats, rng)
        drop = base.pass_rate - head.pass_rate
        naive.append(drop > 1e-12)
        tolerance.append(drop > TOLERANCE + 1e-12)
        gated.append(compare_reports(base, head, GATE.model_copy(update={"seed": i})).failed)
    return scenario, repeats, naive, tolerance, gated


def _rate(flags: list[bool]) -> str:
    return f"{100 * sum(flags) / len(flags):.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sims", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results.md"))
    args = parser.parse_args()

    jobs = [(s, r, args.sims, 1000 * si + r) for si, s in enumerate(SCENARIOS) for r in REPEATS]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(_simulate, jobs))

    lines = [
        f"Share of {args.sims} simulated CI runs that fail, per gate. 20 cases: "
        "12 stable, 4 at 95%, 4 flaky (50-80%). In the 'no change' rows every failure is "
        "a false alarm; in the others every pass is a missed regression.",
        "",
        "| Scenario | Trials per case | Naive (any drop) | Tolerance (> 5 pp) | regressgate |",
        "|---|---|---|---|---|",
    ]
    for scenario, repeats, naive, tolerance, gated in results:
        lines.append(f"| {scenario} | {repeats} | {_rate(naive)} | {_rate(tolerance)} | "
                     f"{_rate(gated)} |")
    text = "\n".join(lines)
    print(text)
    args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
