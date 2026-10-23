from __future__ import annotations

from typing import Any

import pytest

from regressgate.checks import CheckConfigError, get_check
from regressgate.checks.number_checks import extract_numbers
from regressgate.target_result import TargetResult


def run(check_type: str, output: str = "", **params: Any) -> bool:
    return get_check(check_type)(TargetResult(output=output), params).passed


# ---- numbers -------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "value", "unit"), [
    ("Revenue was $130.5B in FY2025.", 130.5e9, "$"),
    ("revenue of 130,497 million", 130_497e6, ""),
    ("grew 114.2% year over year", 114.2, "%"),
    ("a margin of 75 percent", 75.0, "%"),
    ("about 2.5 trillion", 2.5e12, ""),
    ("a loss of -12.5 million", -12.5e6, ""),
])
def test_extract_numbers_understands_scales_units_and_signs(
    text: str, value: float, unit: str
) -> None:
    assert any(n.value == pytest.approx(value) and n.unit == unit for n in extract_numbers(text))


def test_a_year_range_is_not_a_negative_number() -> None:
    assert all(n.value >= 0 for n in extract_numbers("from 2024-2025"))


def test_number_check_respects_tolerance_and_percent_units() -> None:
    assert run("number", "Revenue was $130.5 billion.", value=130_497_000_000, rel_tol=0.01)
    assert not run("number", "Revenue was $120 billion.", value=130_497_000_000, rel_tol=0.01)
    assert run("number", "gross margin of 75.0%", value=75.0, unit="%", abs_tol=0.3)
    # A bare 75 is not a percentage, and a percentage does not satisfy a plain value.
    assert not run("number", "gross margin of 75", value=75.0, unit="%", abs_tol=0.3)
    assert not run("number", "up 75%", value=75.0, abs_tol=0.3)


def test_number_check_rejects_missing_tolerance_and_bad_unit() -> None:
    with pytest.raises(CheckConfigError):
        run("number", "1", value=1)
    with pytest.raises(CheckConfigError):
        run("number", "1", value=1, abs_tol=0, unit="EUR")


# ---- text ----------------------------------------------------------------------------


def test_contains_all_any_and_case() -> None:
    assert run("contains", "TSMC makes the chips", terms=["tsmc", "chips"])
    assert not run("contains", "TSMC makes the chips", terms=["tsmc", "Samsung"])
    assert run("contains", "TSMC makes the chips", terms=["tsmc", "Samsung"], mode="any")
    assert not run("contains", "TSMC", terms=["tsmc"], case_sensitive=True)
    assert run("contains", "TSMC", terms="TSMC")


def test_lead_requires_terms_in_the_first_sentences() -> None:
    answer = "Background first. NVIDIA had the highest margin."
    assert not run("lead", answer, terms=["NVIDIA"])
    assert run("lead", answer, terms=["NVIDIA"], sentences=2)


def test_equals_regex_and_forbidden() -> None:
    assert run("equals", "  Paris\n", value="paris")
    assert not run("equals", "Paris", value="paris", case_sensitive=True)
    assert run("regex", "Order #12345 shipped", pattern=r"#\d{5}")
    assert not run("forbidden", "I can't say, maybe $200B.", patterns=[r"\$\s?\d"])
    assert run("forbidden", "I can't say.", patterns=r"\$\s?\d")
    with pytest.raises(CheckConfigError):
        run("regex", "x", pattern="(")


def test_abstain_matches_refusals_in_the_lead_including_curly_apostrophes() -> None:
    curly = chr(0x2019)
    assert run("abstain", f"I can{curly}t predict FY2028 revenue; any number would be a guess.")
    assert run("abstain", "That company is not in the data I have.")
    assert not run("abstain", "Revenue was $130.5B.")
    # A refusal buried after a confident answer does not count.
    assert not run("abstain", "Revenue will be $300B. It grows. Strictly, I cannot know.")
    assert run("abstain", "Ask me later, pal.", extra_phrases=["ask me later"])


def test_unknown_check_type_lists_known_ones() -> None:
    with pytest.raises(CheckConfigError, match=r"known: .*number"):
        get_check("no-such-check")


def test_missing_required_param() -> None:
    with pytest.raises(CheckConfigError, match="terms"):
        run("contains", "x")


# ---- citations and retrieval ---------------------------------------------------------


def test_citation_matches_on_a_subset_of_fields() -> None:
    result = TargetResult(output="", citations=[{"ticker": "NVDA", "section": "7", "year": 2025}])
    check = get_check("citation")
    assert check(result, {"any_of": [{"ticker": "NVDA", "section": "7"}]}).passed
    assert not check(result, {"any_of": {"ticker": "NVDA", "section": "1A"}}).passed
    with pytest.raises(CheckConfigError):
        check(result, {"any_of": []})


def test_retrieval_scores_reciprocal_rank_and_requires_terms() -> None:
    retrieved = [{"doc": "a", "text": "noise"}, {"doc": "b", "text": "nothing"},
                 {"doc": "b", "text": "TSMC fabs"}]
    result = TargetResult(output="", retrieved=retrieved)
    check = get_check("retrieval")
    hit = check(result, {"any_of": [{"doc": "b"}], "terms": ["tsmc"], "k": 5})
    assert hit.passed and hit.score == pytest.approx(1 / 3)
    assert not check(result, {"any_of": [{"doc": "b"}], "terms": ["tsmc"], "k": 2}).passed
    miss = check(result, {"any_of": [{"doc": "z"}]})
    assert not miss.passed and miss.score == 0.0
