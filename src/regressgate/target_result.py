"""What a target returns for one input. Targets may also return a plain string or a dict."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class TargetResult:
    output: str
    # Sources the answer cites, e.g. [{"doc_id": "a", "section": "7"}]. Checked by `citation`.
    citations: list[dict[str, Any]] = field(default_factory=list)
    # Ranked retrieval results, best first, each optionally with "text". Checked by `retrieval`.
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_FIELDS = {f.name for f in fields(TargetResult)}


def coerce_result(value: Any) -> TargetResult:
    """Accept a TargetResult, a string (the output), or a dict with TargetResult keys.

    Unknown dict keys are kept in `metadata` so nothing a target reports is lost.
    """
    if isinstance(value, TargetResult):
        return value
    if isinstance(value, str):
        return TargetResult(output=value)
    if isinstance(value, dict):
        if "output" not in value:
            raise TypeError("target returned a dict without an 'output' key")
        known = {k: v for k, v in value.items() if k in _FIELDS}
        extra = {k: v for k, v in value.items() if k not in _FIELDS}
        result = TargetResult(**known)
        result.metadata = {**extra, **result.metadata}
        if not isinstance(result.output, str):
            raise TypeError(f"target output must be a string, got {type(result.output).__name__}")
        return result
    raise TypeError(f"target must return str, dict or TargetResult, got {type(value).__name__}")
