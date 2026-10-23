"""`regressgate.yaml`: what to run and how strict the gate is. CLI flags override it.

    target: my_app.eval_target:answer
    cases: evals/cases.jsonl
    repeats: 3
    gate:
      alpha: 0.05
      max_mean_cost_usd: 0.02
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from regressgate.gate import GateConfig
from regressgate.targets import HttpTargetConfig

DEFAULT_CONFIG = Path("regressgate.yaml")


class SuiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str | None = None
    cases: Path | None = None
    repeats: int = Field(3, ge=1)
    concurrency: int = Field(4, ge=1)
    keep_outputs: bool = True
    http: HttpTargetConfig = Field(default_factory=HttpTargetConfig)
    gate: GateConfig = Field(default_factory=GateConfig)


def load_config(path: Path | None) -> SuiteConfig:
    """The given file, else ./regressgate.yaml when present, else defaults."""
    if path is None:
        if not DEFAULT_CONFIG.exists():
            return SuiteConfig()
        path = DEFAULT_CONFIG
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = SuiteConfig.model_validate(data)
    # Relative case paths are relative to the config file, not the working directory.
    if config.cases is not None and not config.cases.is_absolute():
        config.cases = (path.parent / config.cases)
    return config
