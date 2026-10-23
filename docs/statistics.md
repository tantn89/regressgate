# How the gate decides

`regressgate compare BASE HEAD` answers one question: **if nothing had changed, how
surprising would a drop this large be?** It compares only the cases both reports share.

## The two tests

A regression needs a drop larger than `margin` (default 0) in the mean per-case pass rate
**and** evidence from either test below. Each test runs at `alpha / 2` (default 0.025),
so the chance of a false alarm from either is at most `alpha`.

### Aggregate: stratified permutation test

If the change did nothing, then for each case the base trials and the head trials come
from the same distribution and are interchangeable. regressgate pools each case's trials,
reshuffles them between base and head thousands of times (`permutations`, default 10,000),
and recomputes the mean per-case difference each time. The p-value is the share of shuffles
at least as bad as the observed drop.

Why this test:

- **No distributional assumptions.** Pass rates near 100% and small samples are where
  normal approximations and bootstrap percentile intervals break down.
- **Noise is weighed per case.** A case that passed every trial in both runs cannot move
  when shuffled, so it adds no noise. A flaky case moves a lot, so a change in it counts
  for little.
- **One trial per case is handled honestly.** The test becomes an exact sign test on the
  cases that flipped: one flip is never significant; with the default `alpha` it takes
  six flips in the same direction (p = 1/64) and none the other way.

This test catches broad, moderate degradation, for example ten cases each losing one trial
in five.

### Per case: Fisher exact tests with Tarone's correction

An average dilutes a single case that broke completely when other cases are noisy: with
two flaky cases in a suite of twenty, 5/5 to 0/5 on one stable case does not move the mean
enough. So each case also gets a one-sided Fisher exact test of "head pass rate is lower".

Testing twenty cases at once needs a multiple-testing correction, but plain Bonferroni would
divide `alpha` by twenty, including the eighteen cases that passed every trial and cannot
produce evidence of anything. Tarone's correction for discrete tests counts only the cases
whose smallest possible p-value could reach the threshold. In the example above, the
broken case's p-value is 1/252 ≈ 0.004, comfortably below the corrected threshold.

## Verdicts

| Verdict | When | Exit code |
|---|---|---|
| `regression` | Drop > `margin` with evidence from either test, or a hard limit exceeded | 1 |
| `warn` | Drop > `margin` without evidence: probably noise; re-run with more repeats to be sure | 0 (1 with `fail_on: warn`) |
| `improvement` | Gain > `margin` with aggregate evidence | 0 |
| `pass` | Anything else | 0 |

Hard limits (`min_pass_rate`, `max_mean_cost_usd`, `max_p95_latency_s`) are checked on the
head report alone and fail regardless of statistics.

## Choosing repeats

Repeats buy detection power. From the simulation in `benchmarks/` (20 cases, 4 of them
flaky), the share of runs in which a single stable case breaking is caught:

| Trials per case | 1 | 3 | 5 | 10 |
|---|---|---|---|---|
| Detected | 0% | 9% | 92% | 99% |

With three trials the best possible per-case evidence is 3/3 to 0/3, p = 0.05, which is
not below the corrected threshold, so three trials catch a single broken case only when the
aggregate also moves. Five is a good default for gating; three is useful for measuring
noise cheaply.

## Assumptions

- **Trials are independent given the system.** A response cache that returns the same
  answer for repeated inputs makes repeats identical and hides noise; disable it for evals.
- **The case set is fixed.** The verdict is about this suite, not about questions you have
  not written. That is the right question for a regression gate and the wrong one for
  claims like "the model is 95% accurate".
- **Base and head ran in comparable conditions.** Rate limits, timeouts and provider
  outages show up as failed trials; check the `error` field of failing trials before
  trusting a regression.

## Settings

```yaml
gate:
  alpha: 0.05             # overall false-alarm budget
  margin: 0.0             # ignore drops at or below this size (0.02 = 2 pp)
  permutations: 10000
  seed: 0                 # same reports + same seed = same verdict
  fail_on: regression     # or: warn
  min_pass_rate: null
  max_mean_cost_usd: null
  max_p95_latency_s: null
```
