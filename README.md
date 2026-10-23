# regressgate

**Fail CI on real eval regressions, not on LLM noise.**

Your eval went from 19/20 to 18/20. Is the prompt change worse, or did a flaky case just
flip? regressgate runs each case several times, grades every output with deterministic
checks, and fails the build only when a statistical test says the drop is real.

![ci](https://github.com/tantn89/regressgate/actions/workflows/ci.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![license](https://img.shields.io/badge/license-MIT-green)

```text
## regressgate: REGRESSION

Pass rate 97.8% -> 86.7% (-11.1 pp) over 9 shared cases, 5 vs 5 trials per case.
Aggregate permutation p-value for a drop: 0.0241; per-case threshold 0.0250.

| Case     | Base | Head | Change    | Fisher p (worse) | Significant |
| warranty | 5/5  | 0/5  | -100.0 pp | 0.0040           | yes         |
```

Same suite, unchanged code: the flaky `refund-window` case goes 4/5 to 3/5, and the verdict
is `WARN: possible regression, not significant`, exit code 0.

---

## Why a statistical gate

LLM apps are stochastic. Re-running an unchanged system moves its eval score, so a CI rule
like "fail if the score dropped" fails healthy pull requests, and teams learn to ignore it.
Loosening it to "fail if it dropped by more than 5 points" stops the noise and also misses
real breakage.

`benchmarks/false_alarm_simulation.py` measures this on a realistic 20-case suite (12 stable
cases, 4 at 95%, 4 flaky between 50% and 80%), 1,000 simulated CI runs per row:

| Scenario | Trials per case | Naive (any drop) | Tolerance (> 5 pp) | regressgate |
|---|---|---|---|---|
| **No change** (every failure is a false alarm) | 1 | 35% | 13% | **0%** |
| | 5 | 44% | 5% | **2%** |
| | 10 | 48% | 1% | **2%** |
| **One stable case breaks** (-5 pp) | 1 | 61% | 36% | 0% |
| | 5 | 91% | 42% | **92%** |
| | 10 | 98% | 46% | **99%** |
| **Stable cases drop to 85%** (-9 pp) | 1 | 76% | 56% | 3% |
| | 5 | 98% | 78% | 46% |
| | 10 | 100% | 90% | **83%** |

- The naive gate fails 35-48% of pull requests that change nothing. Its high "detection"
  numbers are mostly that same false-alarm rate.
- A fixed tolerance trades noise for blindness: it misses more than half of the runs where
  a case broke completely.
- regressgate keeps false alarms under its 5% budget at every setting, and with 5 trials per
  case it catches a single broken case 92% of the time.
- **With one trial per case, nothing can separate noise from regression.** regressgate says
  so (it will not fail on a single flip) instead of guessing. Repeats buy detection power;
  the full table, including 3 trials, is in [`benchmarks/results.md`](benchmarks/results.md).

## Quickstart

```bash
pip install "git+https://github.com/tantn89/regressgate"   # PyPI release: pip install regressgate
```

1. Describe cases and the checks their outputs must pass (`cases.jsonl`):

```json
{"id": "shipping-cost", "input": "How much is shipping?", "checks": [{"type": "number", "value": 4.99, "unit": "$", "abs_tol": 0.001}]}
{"id": "warranty", "input": "How long is the warranty?", "checks": [{"type": "lead", "terms": ["2-year"]}, {"type": "citation", "any_of": [{"doc": "help/warranty.md"}]}]}
{"id": "unknown", "input": "Do you accept Dogecoin?", "checks": [{"type": "abstain"}]}
```

2. Point regressgate at the system under test, a Python function or an HTTP endpoint
   (`regressgate.yaml`):

```yaml
target: my_app/eval_target.py:answer   # def answer(input) -> str | dict | TargetResult
cases: cases.jsonl
repeats: 5
gate:
  alpha: 0.05
  max_mean_cost_usd: 0.02              # optional hard limits
```

3. Record a baseline once, then gate every change against it:

```bash
regressgate run --out baseline.json          # on main; commit the file
regressgate run --out head.json              # on your branch
regressgate compare baseline.json head.json  # exit 1 only on a real regression
```

A complete offline example (no API key) lives in [`examples/support_bot`](examples/support_bot):
`regressgate run -c examples/support_bot/regressgate.yaml`, then try it with
`SUPPORT_BOT_VARIANT=broken`.

## In CI

```yaml
permissions:
  contents: read
  pull-requests: write          # for the PR comment
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: "3.12" }
  - run: pip install -e .       # your app
  - uses: tantn89/regressgate@v0.1.0
    with:
      config: regressgate.yaml
      baseline: evals/baseline.json
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The action writes the verdict and run details to the job summary, posts (and on later
pushes, updates) one PR comment, and exposes `verdict` and `failed` outputs. This repository
runs it on its own example in [`ci.yml`](.github/workflows/ci.yml), including a broken
variant that must fail.

**Where the baseline lives.** Commit it. Updating the baseline is then a reviewed change in
a pull request diff, not a side effect of whichever run happened last on main.

## How the gate decides

A drop counts as a regression only when it is larger than `margin` (default 0) **and** one
of two tests finds evidence, each at `alpha / 2` so the overall false-alarm rate stays at
or below `alpha`:

1. **Aggregate: stratified permutation test.** If nothing changed, a case's base and head
   trials are interchangeable. Shuffling them within each case thousands of times gives the
   distribution of the mean pass-rate difference under "no change", and the observed drop
   is compared against it. Cases that passed every trial in both runs cannot move, so they
   add no noise; flaky cases move a lot, so they are discounted automatically. With one
   trial per case this reduces to an exact sign test.
2. **Per case: one-sided Fisher exact tests with Tarone's correction.** An average can
   hide one case that broke completely behind a few noisy ones. Each case gets an exact
   test, and the multiple-testing penalty counts only the cases that could ever reach
   significance, so twenty always-passing cases do not dilute the evidence from the one
   that went 5/5 to 0/5.

A drop without evidence is `warn` (exit 0, visible in the summary; `fail_on: warn` makes it
fail). A significant gain is `improvement`. `min_pass_rate`, `max_mean_cost_usd` and
`max_p95_latency_s` are hard limits that fail regardless of statistics. Everything is
seeded, so the same two reports always give the same verdict.

Assumptions, stated plainly: trials of a case are independent given the system (no shared
cache that makes repeats identical), and the case set is fixed, so the verdict is about
*this* suite, not a population of future questions.

## Checks

| Type | Passes when | Key params |
|---|---|---|
| `contains` | all (or any) terms appear | `terms`, `mode`, `case_sensitive` |
| `lead` | terms appear in the first N sentences: answer first | `terms`, `sentences` (1) |
| `equals` | output equals the value after whitespace and case normalisation | `value` |
| `regex` / `forbidden` | a pattern matches / none of the patterns match | `pattern` / `patterns` |
| `number` | a stated figure is within tolerance; understands `$130.5B`, `130,497 million`, `75%` | `value`, `rel_tol` or `abs_tol`, `unit` |
| `abstain` | the output declines to answer, within its lead | `sentences` (2), `extra_phrases` |
| `citation` | a cited source matches the expected fields | `any_of` |
| `retrieval` | a matching item ranks within k; score is reciprocal rank (pass rate = recall@k, mean = MRR) | `any_of`, `k`, `terms` |

Add your own with a decorator, or ship one in a package through the `regressgate.checks`
entry-point group:

```python
from regressgate import CheckOutcome, TargetResult, check

@check("json_valid")
def json_valid(result: TargetResult, params: dict) -> CheckOutcome:
    import json
    try:
        json.loads(result.output)
        return CheckOutcome(True)
    except ValueError as e:
        return CheckOutcome(False, detail=str(e))
```

## Targets

- **Python:** `package.module:function` or `path/to/file.py:function`. The function takes
  the case `input` (a string or a dict) and returns a string, a dict with `output` and
  optional `citations`, `retrieved`, `cost_usd`, token counts, or a `TargetResult`.
- **HTTP:** a URL. Configure the request field, headers (with `${ENV_VAR}` expansion for
  secrets, which never reach the report) and where the answer, citations and cost sit in
  the JSON response under `http:` in `regressgate.yaml`.

A target exception fails that trial and is recorded; an invalid check config aborts the run
before any target call spends money.

## Design decisions

- **Deterministic checks only.** An LLM judge adds its own noise and drift to the very
  number the gate is trying to stabilise. Judges are on the roadmap as an opt-in check, not
  the default.
- **Permutation and exact tests instead of normal approximations.** Eval suites are small
  (tens of cases, a handful of trials) and pass rates sit near 100%, exactly where z-tests
  and bootstrap percentile intervals misbehave.
- **Pure Python, three dependencies** (pydantic, PyYAML, Typer; httpx optional). A gate
  decision with 10,000 shuffles takes well under a second; numpy would add weight, not speed.
- **Versioned JSON reports** are the unit of comparison, so a baseline can come from a file
  in git, a CI artifact, or another machine.

## Roadmap

- [ ] Opt-in LLM-judge check with its own repeat-and-agree logic
- [ ] Power analysis: "how many repeats do I need to detect a 5 pp drop?"
- [ ] Per-tag verdicts (for example, gate `abstain` cases separately)
- [ ] Baseline from the latest successful run on the default branch

## License

MIT
