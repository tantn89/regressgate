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
    # Directory of the config file; relative paths in the file resolve against it.
    base_dir: Path = Field(default=Path("."), exclude=True)

    def cases_path(self) -> Path | None:
        if self.cases is None or self.cases.is_absolute():
            return self.cases
        return self.base_dir / self.cases

    def target_spec(self) -> str | None:
        return resolve_relative(self.target, self.base_dir) if self.target else None


def load_config(path: Path | None) -> SuiteConfig:
    """The given file, else ./regressgate.yaml when present, else defaults."""
    if path is None:
        if not DEFAULT_CONFIG.exists():
            return SuiteConfig()
        path = DEFAULT_CONFIG
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = SuiteConfig.model_validate(data)
    config.base_dir = path.parent
    return config


def resolve_relative(spec: str, base_dir: Path) -> str:
    """A `file.py:function` target relative to `base_dir`; other specs unchanged.

    File paths in a config are relative to the config file, so a suite runs the same from
    any working directory. The unresolved spec is what reports record, so they never
    contain a machine-specific absolute path.
    """
    if spec.startswith(("http://", "https://")):
        return spec
    module_part, sep, attr = spec.rpartition(":")
    if sep and module_part.endswith(".py") and not Path(module_part).is_absolute():
        return f"{base_dir / module_part}:{attr}"
    return spec
