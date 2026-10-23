"""`number`: the output states a figure within tolerance of the expected value.

Understands thousands separators, decimals, a leading minus, `$`, `%` / percent and scale
words (thousand, million, billion, trillion and k/m/bn/b/t), so "$130.5B" and
"130,497 million" both match 130_497_000_000.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from regressgate.checks import CheckConfigError, CheckOutcome, check, require
from regressgate.target_result import TargetResult

_SCALE = {"trillion": 1e12, "t": 1e12, "billion": 1e9, "bn": 1e9, "b": 1e9,
          "million": 1e6, "mn": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
_NUMBER = re.compile(
    r"(?:(?<![\w.])(?P<sign>-))?(?P<dollar>\$)?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d+))?\s?"
    r"(?P<suffix>%|(?:percent|trillion|billion|million|thousand|bn|mn|[tbmk])\b)?",
    re.IGNORECASE,
)
_MINUS_SIGN = chr(0x2212)


@dataclass(frozen=True)
class ExtractedNumber:
    value: float
    unit: str  # "%" | "$" | ""


def extract_numbers(text: str) -> list[ExtractedNumber]:
    found = []
    for m in _NUMBER.finditer(text.replace(_MINUS_SIGN, "-")):
        value = float(m.group("num").replace(",", "") + "." + (m.group("dec") or "0"))
        if m.group("sign"):
            value = -value
        suffix = (m.group("suffix") or "").lower()
        if suffix in ("%", "percent"):
            found.append(ExtractedNumber(value, "%"))
            continue
        if suffix in _SCALE:
            value *= _SCALE[suffix]
        found.append(ExtractedNumber(value, "$" if m.group("dollar") else ""))
    return found


def number_matches(
    target: float, found: list[ExtractedNumber], *, unit: str = "",
    rel_tol: float | None = None, abs_tol: float | None = None,
) -> ExtractedNumber | None:
    """The first extracted number within tolerance. A percentage only matches unit "%"."""
    for n in found:
        if (unit == "%") != (n.unit == "%"):
            continue
        if abs_tol is not None and abs(n.value - target) <= abs_tol:
            return n
        if rel_tol is not None and abs(n.value - target) <= rel_tol * abs(target):
            return n
    return None


@check("number")
def number_check(result: TargetResult, params: dict[str, Any]) -> CheckOutcome:
    target = float(require(params, "value"))
    unit = str(params.get("unit", ""))
    if unit not in ("", "$", "%"):
        raise CheckConfigError(f"unit must be '', '$' or '%', got {unit!r}")
    rel_tol, abs_tol = params.get("rel_tol"), params.get("abs_tol")
    if rel_tol is None and abs_tol is None:
        raise CheckConfigError("set rel_tol or abs_tol")
    found = extract_numbers(result.output)
    hit = number_matches(
        target, found, unit=unit,
        rel_tol=None if rel_tol is None else float(rel_tol),
        abs_tol=None if abs_tol is None else float(abs_tol),
    )
    if hit:
        return CheckOutcome(True, detail=f"found {hit.value:g}{hit.unit}")
    return CheckOutcome(False, detail=f"no number near {target:g}{unit} among {len(found)} found")
