"""Eval cases: an input for the target plus the deterministic checks its output must pass.

Cases live in JSONL (one object per line) or YAML (a list of objects):

    {"id": "nvda-revenue", "input": "What was NVIDIA's revenue in FY2025?",
     "checks": [{"type": "number", "value": 130497000000, "rel_tol": 0.01}]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CaseFileError(ValueError):
    """A case file that cannot be loaded; the message names the file and line or index."""


class CheckSpec(BaseModel):
    """One check: its registered `type`, an optional report label, and type-specific params."""

    model_config = ConfigDict(extra="allow", frozen=True)

    type: str
    name: str | None = None

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    input: str | dict[str, Any]
    checks: list[CheckSpec] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def check_labels(self) -> list[str]:
        """Report labels per check: `name`, else `type`, suffixed with #2, #3 when repeated."""
        labels: list[str] = []
        for spec in self.checks:
            base = spec.name or spec.type
            label, n = base, 1
            while label in labels:
                n += 1
                label = f"{base}#{n}"
            labels.append(label)
        return labels


def load_cases(path: str | Path) -> list[Case]:
    path = Path(path)
    if not path.exists():
        raise CaseFileError(f"{path}: file not found")
    raw = _read_raw(path)
    cases: list[Case] = []
    for where, obj in raw:
        try:
            cases.append(Case.model_validate(obj))
        except ValidationError as e:
            raise CaseFileError(f"{path} {where}: {e}") from None
    if not cases:
        raise CaseFileError(f"{path}: no cases")
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise CaseFileError(f"{path}: duplicate case id {case.id!r}")
        seen.add(case.id)
    return cases


def _read_raw(path: Path) -> list[tuple[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
        if not isinstance(data, list):
            raise CaseFileError(f"{path}: expected a YAML list of cases")
        return [(f"item {i}", obj) for i, obj in enumerate(data, start=1)]
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            rows.append((f"line {lineno}", json.loads(line)))
        except json.JSONDecodeError as e:
            raise CaseFileError(f"{path} line {lineno}: invalid JSON ({e.msg})") from None
    return rows
