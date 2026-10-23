from __future__ import annotations

import pytest

from conftest import make_report
from regressgate.gate import GateConfig, compare_reports
from regressgate.markdown_report import COMMENT_MARKER, render_gate

CONFIG = GateConfig(permutations=5000)
BASE = {f"case-{i}": (5, 5) for i in range(18)} | {"flaky-a": (3, 5), "flaky-b": (2, 5)}


def test_identical_runs_pass() -> None:
    result = compare_reports(make_report(BASE), make_report(BASE), CONFIG)
    assert result.verdict == "pass" and not result.failed and result.changes == []


def test_a_broken_stable_case_is_a_regression() -> None:
    head = BASE | {"case-0": (0, 5)}
    result = compare_reports(make_report(BASE), make_report(head), CONFIG)
    assert result.verdict == "regression" and result.failed
    assert result.changes[0].id == "case-0" and result.changes[0].significant
    # The flaky cases add enough noise that the aggregate test alone would miss it.
    assert result.p_worse > 0.025
    assert "REGRESSION" in render_gate(result)


def test_broad_moderate_degradation_is_caught_by_the_aggregate_test() -> None:
    base = {f"c{i}": (5, 5) for i in range(20)}
    head = {f"c{i}": (4, 5) if i < 10 else (5, 5) for i in range(20)}  # 10 cases lose one pass
    result = compare_reports(make_report(base), make_report(head), CONFIG)
    assert not any(c.significant for c in result.changes)
    assert result.p_worse < 0.025 and result.verdict == "regression"


def test_flaky_noise_is_a_warning_not_a_failure() -> None:
    head = BASE | {"flaky-a": (1, 5)}
    result = compare_reports(make_report(BASE), make_report(head), CONFIG)
    assert result.verdict == "warn" and not result.failed
    assert any("within noise" in n for n in result.notes)


def test_fail_on_warn_makes_warnings_fail() -> None:
    head = BASE | {"flaky-a": (1, 5)}
    result = compare_reports(make_report(BASE), make_report(head),
                             CONFIG.model_copy(update={"fail_on": "warn"}))
    assert result.verdict == "warn" and result.failed


def test_margin_ignores_small_significant_drops() -> None:
    head = BASE | {"case-0": (0, 5)}  # -5 pp, significant
    result = compare_reports(make_report(BASE), make_report(head),
                             CONFIG.model_copy(update={"margin": 0.1}))
    assert result.verdict == "pass"


def test_improvement() -> None:
    base = {f"c{i}": (0, 5) for i in range(5)} | {f"s{i}": (5, 5) for i in range(5)}
    head = {f"c{i}": (5, 5) for i in range(5)} | {f"s{i}": (5, 5) for i in range(5)}
    result = compare_reports(make_report(base), make_report(head), CONFIG)
    assert result.verdict == "improvement" and not result.failed


def test_limits_fail_regardless_of_statistics() -> None:
    report = make_report(BASE, latency_s=3.0, cost_usd=0.05)
    config = CONFIG.model_copy(update={"min_pass_rate": 0.99, "max_mean_cost_usd": 0.01,
                                       "max_p95_latency_s": 2.0})
    result = compare_reports(make_report(BASE), report, config)
    assert result.verdict == "regression"
    assert len(result.limit_failures) == 3


def test_only_shared_cases_are_compared() -> None:
    base = {"a": (1, 1), "b": (1, 1)}
    head = {"a": (1, 1), "c": (0, 1)}
    result = compare_reports(make_report(base), make_report(head), CONFIG)
    assert result.cases_compared == 1 and result.added == ["c"] and result.removed == ["b"]
    assert "Not compared" in render_gate(result)
    with pytest.raises(ValueError):
        compare_reports(make_report({"x": (1, 1)}), make_report({"y": (1, 1)}), CONFIG)


def test_low_repeats_note_and_comment_marker() -> None:
    result = compare_reports(make_report({"a": (1, 1)}), make_report({"a": (1, 1)}), CONFIG)
    text = render_gate(result)
    assert text.startswith(COMMENT_MARKER)
    assert "Fewer than 3 trials" in text
