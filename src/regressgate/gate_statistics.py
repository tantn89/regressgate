"""Statistics behind the gate. Pure Python, seeded, so a verdict is reproducible.

The question a regression gate must answer is: "if nothing had changed, how often would
the head run look at least this much worse than the base run?" The case set is fixed (it
is the benchmark), so the only randomness is in the target's outputs. That makes a
*stratified permutation test* the natural tool: under "no change", a case's base and head
trials are interchangeable, so we shuffle each case's pooled trials between the two runs
and recompute the mean per-case pass-rate difference many times.

Consequences, by design:
- cases that passed (or failed) every trial in both runs cannot move and add no noise;
- a flaky case (3/5 -> 1/5) contributes mostly noise, because shuffling it moves a lot;
- with one trial per case the test reduces to an exact sign test on the flipped cases,
  so a single flip is never "significant", which is the honest answer.

Averaging dilutes one broken case among noisy ones, so the gate pairs this with per-case
Fisher exact tests under Tarone's correction (`min_achievable_p`, `tarone_threshold`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class CaseCounts:
    """Passes out of trials for one case in one run."""

    passes: int
    trials: int

    @property
    def rate(self) -> float:
        return self.passes / self.trials


@dataclass(frozen=True)
class PermutationResult:
    delta: float  # mean over cases of (head rate - base rate); negative = worse
    p_worse: float  # P(delta_perm <= delta | no change)
    p_better: float  # P(delta_perm >= delta | no change)
    permutations: int


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float
    confidence: float


def mean_delta(base: list[CaseCounts], head: list[CaseCounts]) -> float:
    return sum(h.rate - b.rate for b, h in zip(base, head, strict=True)) / len(base)


def _hypergeometric(rng: random.Random, population: int, successes: int, draws: int) -> int:
    """Successes in `draws` items taken without replacement from the pooled trials."""
    return sum(1 for i in rng.sample(range(population), draws) if i < successes)


def permutation_test(
    base: list[CaseCounts], head: list[CaseCounts], *, permutations: int = 10_000, seed: int = 0
) -> PermutationResult:
    if not base or len(base) != len(head):
        raise ValueError("base and head need the same, non-empty list of cases")
    observed = mean_delta(base, head)
    n_cases = len(base)
    # Cases whose pooled trials are all passes or all fails cannot move under shuffling.
    movable: list[tuple[CaseCounts, CaseCounts]] = []
    fixed_sum = 0.0
    for b, h in zip(base, head, strict=True):
        if 0 < b.passes + h.passes < b.trials + h.trials:
            movable.append((b, h))
        else:
            fixed_sum += h.rate - b.rate
    rng = random.Random(seed)
    worse = better = 0
    tolerance = 1e-12  # ties count toward both tails
    for _ in range(permutations):
        total = fixed_sum
        for b, h in movable:
            pooled_n, pooled_s = b.trials + h.trials, b.passes + h.passes
            head_s = _hypergeometric(rng, pooled_n, pooled_s, h.trials)
            total += head_s / h.trials - (pooled_s - head_s) / b.trials
        delta = total / n_cases
        worse += delta <= observed + tolerance
        better += delta >= observed - tolerance
    # Add-one so a p-value is never exactly zero from a finite number of shuffles.
    return PermutationResult(
        delta=observed,
        p_worse=(worse + 1) / (permutations + 1),
        p_better=(better + 1) / (permutations + 1),
        permutations=permutations,
    )


def _fisher_tail(base: CaseCounts, head: CaseCounts, head_passes: int) -> float:
    population, successes, draws = base.trials + head.trials, base.passes + head.passes, head.trials
    low = max(0, draws - (population - successes))
    total = comb(population, draws)
    return sum(
        comb(successes, x) * comb(population - successes, draws - x)
        for x in range(low, head_passes + 1)
    ) / total


def fisher_worse(base: CaseCounts, head: CaseCounts) -> float:
    """One-sided Fisher exact p-value that one case's head pass rate is below its base rate."""
    return _fisher_tail(base, head, head.passes)


def min_achievable_p(base: CaseCounts, head: CaseCounts) -> float:
    """The smallest p-value this case could produce given its pooled trials. A case that
    passed (or failed) every trial in both runs cannot produce any evidence at all."""
    population, successes = base.trials + head.trials, base.passes + head.passes
    return _fisher_tail(base, head, max(0, head.trials - (population - successes)))


def tarone_threshold(min_ps: list[float], alpha: float) -> float:
    """Per-case significance threshold controlling the family-wise error rate at `alpha`.

    Tarone's correction for discrete tests: Bonferroni over only the K cases that could
    reach significance at alpha / K, so twenty always-passing cases do not dilute the
    evidence from the one that broke.
    """
    for k in range(1, len(min_ps) + 1):
        if sum(p <= alpha / k for p in min_ps) <= k:
            return alpha / k
    return alpha / max(1, len(min_ps))


def rerun_interval(
    cases: list[CaseCounts], *, confidence: float = 0.95, resamples: int = 4_000, seed: int = 0
) -> Interval | None:
    """Where the pass rate would land on a re-run of the same cases: resample each case's
    trials with replacement. None with one trial per case, where it cannot be estimated."""
    if not cases:
        raise ValueError("no cases")
    estimate = sum(c.rate for c in cases) / len(cases)
    if all(c.trials < 2 for c in cases):
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        total = 0.0
        for c in cases:
            p = c.rate
            total += sum(rng.random() < p for _ in range(c.trials)) / c.trials
        draws.append(total / len(cases))
    draws.sort()
    tail = (1 - confidence) / 2
    low = draws[int(tail * (resamples - 1))]
    high = draws[int((1 - tail) * (resamples - 1))]
    return Interval(estimate, min(low, estimate), max(high, estimate), confidence)
