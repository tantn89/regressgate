from __future__ import annotations

import pytest

from regressgate.gate_statistics import (
    CaseCounts,
    fisher_worse,
    min_achievable_p,
    permutation_test,
    rerun_interval,
    tarone_threshold,
)

STABLE = CaseCounts(5, 5)


def test_fisher_matches_hand_computed_values() -> None:
    assert fisher_worse(CaseCounts(5, 5), CaseCounts(0, 5)) == pytest.approx(1 / 252)
    assert fisher_worse(CaseCounts(5, 5), CaseCounts(1, 5)) == pytest.approx(6 / 252)
    assert fisher_worse(CaseCounts(3, 5), CaseCounts(3, 5)) > 0.5
    assert fisher_worse(CaseCounts(0, 5), CaseCounts(5, 5)) == pytest.approx(1.0)


def test_no_change_is_not_significant() -> None:
    base = [STABLE] * 15 + [CaseCounts(3, 5)] * 5
    result = permutation_test(base, list(base), permutations=2000)
    assert result.delta == 0
    assert result.p_worse > 0.4 and result.p_better > 0.4


def test_one_stable_case_breaking_is_significant_on_its_own() -> None:
    base = [STABLE] * 20
    head = [STABLE] * 19 + [CaseCounts(0, 5)]
    result = permutation_test(base, head, permutations=20_000)
    assert result.delta == pytest.approx(-0.05)
    # Exact answer: 1 / C(10, 5) = 1/252 ~ 0.004.
    assert result.p_worse == pytest.approx(1 / 252, abs=0.002)


def test_flaky_cases_wobbling_are_not_significant() -> None:
    base = [STABLE] * 15 + [CaseCounts(3, 5)] * 5
    head = [STABLE] * 15 + [CaseCounts(2, 5)] * 5  # each flaky case lost one pass
    result = permutation_test(base, head, permutations=5000)
    assert result.delta < 0
    assert result.p_worse > 0.05


def test_one_trial_per_case_reduces_to_an_exact_sign_test() -> None:
    base = [CaseCounts(1, 1)] * 20
    four_flips = [CaseCounts(1, 1)] * 16 + [CaseCounts(0, 1)] * 4
    five_flips = [CaseCounts(1, 1)] * 15 + [CaseCounts(0, 1)] * 5
    assert permutation_test(base, four_flips, permutations=20_000).p_worse == pytest.approx(
        1 / 16, abs=0.01)
    assert permutation_test(base, five_flips, permutations=20_000).p_worse == pytest.approx(
        1 / 32, abs=0.006)


def test_unequal_repeats_are_supported() -> None:
    result = permutation_test([CaseCounts(3, 3)] * 10, [CaseCounts(5, 5)] * 10, permutations=200)
    assert result.delta == 0 and result.p_worse == 1.0


def test_permutation_test_is_reproducible_by_seed() -> None:
    base = [CaseCounts(3, 5), CaseCounts(4, 5), STABLE]
    head = [CaseCounts(2, 5), CaseCounts(4, 5), CaseCounts(4, 5)]
    a = permutation_test(base, head, permutations=500, seed=7)
    b = permutation_test(base, head, permutations=500, seed=7)
    assert a == b


def test_permutation_test_validates_inputs() -> None:
    with pytest.raises(ValueError):
        permutation_test([], [])
    with pytest.raises(ValueError):
        permutation_test([STABLE], [STABLE, STABLE])


def test_min_achievable_p_and_tarone_ignore_cases_that_cannot_move() -> None:
    assert min_achievable_p(STABLE, STABLE) == 1.0
    assert min_achievable_p(STABLE, CaseCounts(0, 5)) == pytest.approx(1 / 252)
    # 20 stable cases and one broken one: only the broken case counts, so no penalty.
    assert tarone_threshold([1.0] * 20 + [1 / 252], 0.025) == 0.025
    # Three cases that could all reach significance share the budget.
    assert tarone_threshold([0.001, 0.001, 0.001], 0.03) == pytest.approx(0.01)


def test_rerun_interval() -> None:
    assert rerun_interval([CaseCounts(1, 1), CaseCounts(0, 1)]) is None
    stable = rerun_interval([STABLE] * 10)
    assert stable is not None and stable.low == stable.high == 1.0
    noisy = rerun_interval([CaseCounts(3, 5)] * 10, resamples=1000)
    assert noisy is not None and noisy.low < 0.6 < noisy.high
    with pytest.raises(ValueError):
        rerun_interval([])
