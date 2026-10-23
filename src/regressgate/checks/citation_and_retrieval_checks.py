"""`citation` and `retrieval`: did the answer cite, and did retrieval rank, the right source.

Sources are dicts; an expected source matches an item when every expected field is equal,
so {"ticker": "NVDA", "section": "7"} matches any NVDA Item 7 passage regardless of year.
"""

from __future__ import annotations

from typing import Any

from regressgate.checks import CheckConfigError, CheckOutcome, check, require
from regressgate.target_result import TargetResult


def _expected(params: dict[str, Any]) -> list[dict[str, Any]]:
    any_of = require(params, "any_of")
    if isinstance(any_of, dict):
        any_of = [any_of]
    if not isinstance(any_of, list) or not any_of or not all(isinstance(e, dict) for e in any_of):
        raise CheckConfigError("any_of must be a non-empty list of field mappings")
    return any_of


def matches(item: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(k in item and item[k] == v for k, v in expected.items())


def _has_terms(item: dict[str, Any], terms: list[str]) -> bool:
    text = str(item.get("text", "")).lower()
    return all(t.lower() in text for t in terms)


@check("citation")
def citation_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    expected = _expected(params)
    hit = any(matches(c, e) for c in result.citations for e in expected)
    detail = "" if hit else f"none of {len(result.citations)} citations match {expected}"
    return CheckOutcome(hit, detail=detail)


@check("retrieval")
def retrieval_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    """A matching item (optionally containing all `terms` in its text) ranks within `k`.

    The score is the reciprocal rank (0 when absent), so its mean across cases is MRR and
    the pass rate is recall@k.
    """
    expected = _expected(params)
    k = int(params.get("k", 5))
    terms = [str(t) for t in params.get("terms", [])]
    for rank, item in enumerate(result.retrieved, start=1):
        if any(matches(item, e) for e in expected) and _has_terms(item, terms):
            return CheckOutcome(rank <= k, score=1.0 / rank, detail=f"rank {rank}")
    return CheckOutcome(False, score=0.0, detail=f"not in {len(result.retrieved)} results")
