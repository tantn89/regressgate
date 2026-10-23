"""Text checks on the target's output: contains, lead, equals, regex, forbidden, abstain."""

from __future__ import annotations

import re
from typing import Any

from regressgate.checks import CheckConfigError, CheckOutcome, check, require
from regressgate.target_result import TargetResult

# Phrases that signal a refusal to answer from outside the available data. Matched after
# curly apostrophes are normalised. Extend per suite with `extra_phrases`.
DEFAULT_ABSTAIN_PATTERNS = (
    r"not (?:available|in|included|contain|have)",
    r"no (?:\w+ )?(?:data|information|record)",
    r"(?:don|doesn)'t have|do not have|has no",
    r"unable to",
    r"isn't (?:available|in)",
    r"(?:cannot|can't|won't) (?:tell|give|predict|forecast|provide|say|know|answer)",
    r"outside (?:the|my) (?:data|knowledge|sources)",
    r"would be a guess|rather not (?:quote|guess)",
    r"i don't know|not sure",
)
_CURLY_APOSTROPHE = chr(0x2019)


def _normalise(text: str) -> str:
    return text.replace(_CURLY_APOSTROPHE, "'")


def lead(text: str, sentences: int) -> str:
    """The first `sentences` sentences: where a direct answer or a refusal belongs."""
    return " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:sentences])


def _terms(params: dict[str, Any]) -> list[str]:
    terms = require(params, "terms")
    if isinstance(terms, str):
        terms = [terms]
    if not isinstance(terms, list) or not terms:
        raise CheckConfigError("terms must be a non-empty list of strings")
    return [str(t) for t in terms]


def _contains(text: str, terms: list[str], params: dict[str, Any]) -> CheckOutcome:
    case_sensitive = bool(params.get("case_sensitive", False))
    mode = params.get("mode", "all")
    if mode not in ("all", "any"):
        raise CheckConfigError(f"mode must be 'all' or 'any', got {mode!r}")
    haystack = text if case_sensitive else text.lower()
    present = [t for t in terms if (t if case_sensitive else t.lower()) in haystack]
    missing = [t for t in terms if t not in present]
    passed = bool(present) if mode == "any" else not missing
    return CheckOutcome(passed, detail="" if passed else f"missing {missing}")


@check("contains")
def contains_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    return _contains(_normalise(result.output), _terms(params), params)


@check("lead")
def lead_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    """Terms must appear in the first `sentences` sentences (default 1): answer first."""
    sentences = int(params.get("sentences", 1))
    return _contains(lead(_normalise(result.output), sentences), _terms(params), params)


@check("equals")
def equals_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    expected = str(require(params, "value"))
    got = result.output
    if not params.get("case_sensitive", False):
        expected, got = expected.lower(), got.lower()
    if params.get("strip", True):
        expected, got = " ".join(expected.split()), " ".join(got.split())
    return CheckOutcome(got == expected, detail="" if got == expected else f"got {got[:80]!r}")


def _compile(pattern: Any) -> re.Pattern[str]:
    try:
        return re.compile(str(pattern), re.IGNORECASE)
    except re.error as e:
        raise CheckConfigError(f"invalid regex {pattern!r}: {e}") from None


@check("regex")
def regex_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    pattern = _compile(require(params, "pattern"))
    passed = bool(pattern.search(_normalise(result.output)))
    return CheckOutcome(passed, detail="" if passed else f"no match for {pattern.pattern!r}")


@check("forbidden")
def forbidden_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    """None of `patterns` may appear, e.g. a refusal that still quotes an invented figure."""
    patterns = require(params, "patterns")
    if isinstance(patterns, str):
        patterns = [patterns]
    text = _normalise(result.output)
    hits = [p for p in patterns if _compile(p).search(text)]
    return CheckOutcome(not hits, detail=f"matched {hits}" if hits else "")


@check("abstain")
def abstain_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    """The output declines to answer within its first `sentences` sentences (default 2)."""
    sentences = int(params.get("sentences", 2))
    patterns = [*DEFAULT_ABSTAIN_PATTERNS, *params.get("extra_phrases", [])]
    regex = _compile("|".join(f"(?:{p})" for p in patterns))
    passed = bool(regex.search(lead(_normalise(result.output), sentences)))
    return CheckOutcome(passed, detail="" if passed else "no refusal in the lead")
