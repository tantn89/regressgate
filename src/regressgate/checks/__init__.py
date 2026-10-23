"""Check registry. A check maps (target result, params) to a pass/fail outcome.

Built-in checks register on import. Third-party packages can add checks through the
`regressgate.checks` entry-point group, or in-process with the `@check("name")` decorator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from regressgate.case_schema import Case
from regressgate.target_result import TargetResult


@dataclass(frozen=True)
class CheckOutcome:
    passed: bool
    score: float | None = None  # optional graded value in [0, 1], e.g. reciprocal rank
    detail: str = ""


class CheckConfigError(ValueError):
    """A check's params are invalid. Raised before or during a run; never scored as a fail."""


CheckFn = Callable[[TargetResult, dict[str, Any]], CheckOutcome]
_REGISTRY: dict[str, CheckFn] = {}
_PLUGINS_LOADED = False


def check(name: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        _REGISTRY[name] = fn
        return fn

    return register


def get_check(name: str) -> CheckFn:
    global _PLUGINS_LOADED
    if name not in _REGISTRY and not _PLUGINS_LOADED:
        _PLUGINS_LOADED = True
        for ep in entry_points(group="regressgate.checks"):
            _REGISTRY.setdefault(ep.name, ep.load())
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise CheckConfigError(f"unknown check type {name!r} (known: {known})")
    return _REGISTRY[name]


def validate_cases(cases: list[Case]) -> None:
    """Fail fast on unknown check types, before any target call spends money."""
    for case in cases:
        for spec in case.checks:
            try:
                get_check(spec.type)
            except CheckConfigError as e:
                raise CheckConfigError(f"case {case.id!r}: {e}") from None


def run_checks(case: Case, result: TargetResult) -> dict[str, CheckOutcome]:
    outcomes = {}
    for label, spec in zip(case.check_labels(), case.checks, strict=True):
        try:
            outcomes[label] = get_check(spec.type)(result, spec.params)
        except CheckConfigError as e:
            raise CheckConfigError(f"case {case.id!r}, check {label!r}: {e}") from None
    return outcomes


def require(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise CheckConfigError(f"missing required param {key!r}")
    return params[key]


# Register built-ins.
from regressgate.checks import (  # noqa: E402
    citation_and_retrieval_checks,
    number_checks,
    text_checks,
)

__all__ = [
    "CheckConfigError",
    "CheckFn",
    "CheckOutcome",
    "check",
    "citation_and_retrieval_checks",
    "get_check",
    "number_checks",
    "require",
    "run_checks",
    "text_checks",
    "validate_cases",
]
