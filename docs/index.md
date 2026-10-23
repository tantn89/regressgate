# regressgate

**Fail CI on real eval regressions, not on LLM noise.**

An LLM app's eval score moves when nothing changed. A gate that fails on any drop fails
healthy pull requests; a gate with a fixed tolerance misses real breakage. regressgate
runs each case several times, grades outputs with deterministic checks, and fails only
when a statistical test says the drop is real.

On a simulated 20-case suite with typical noise, a "fail on any drop" gate fails **35-48%**
of pull requests that change nothing. regressgate keeps that under **2%**, and with five
trials per case still catches a single broken case **92%** of the time. The simulation and
its full results are in the repository under `benchmarks/`.

```bash
pip install regressgate
regressgate run --out baseline.json          # once, on main
regressgate run --out head.json              # on a change
regressgate compare baseline.json head.json  # exit 1 only on a real regression
```

- [Getting started](getting-started.md): a suite, a target and a first gate in five minutes.
- [Cases and checks](cases-and-checks.md): the case file format and every built-in check.
- [How the gate decides](statistics.md): the tests behind a verdict, and their assumptions.
- [GitHub Action](github-action.md): job summaries, PR comments, baselines.
- [Custom checks and targets](extending.md): plug in your own grading and systems.

regressgate is MIT-licensed and has three runtime dependencies (pydantic, PyYAML, Typer).
