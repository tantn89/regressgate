"""Targets: the system under test, called once per trial with a case's input.

Two kinds, chosen by the spec string:
- `package.module:function` or `path/to/file.py:function`: an in-process Python callable.
- `http://...` / `https://...`: an HTTP endpoint that takes and returns JSON.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from regressgate.target_result import TargetResult, coerce_result

Target = Callable[[Any], TargetResult]


class TargetError(ValueError):
    """The target spec cannot be resolved (bad module path, missing function, missing env)."""


class HttpTargetConfig(BaseModel):
    """How to call an HTTP target and where the answer sits in its JSON response."""

    method: str = "POST"
    input_field: str = "input"  # request body: {input_field: case.input}
    headers: dict[str, str] = Field(default_factory=dict)  # values may use ${ENV_VAR}
    timeout_s: float = 120.0
    output_path: str = "output"  # dotted paths into the response JSON
    citations_path: str | None = None
    retrieved_path: str | None = None
    cost_path: str | None = None


def load_target(spec: str, http: HttpTargetConfig | None = None) -> Target:
    if spec.startswith(("http://", "https://")):
        return _http_target(spec, http or HttpTargetConfig())
    return _python_target(spec)


def _python_target(spec: str) -> Target:
    module_part, sep, attr = spec.rpartition(":")
    if not sep or not module_part or not attr:
        raise TargetError(f"target {spec!r} must look like 'package.module:function'")
    if module_part.endswith(".py"):
        path = Path(module_part).resolve()
        if not path.exists():
            raise TargetError(f"target file not found: {path}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        if module_spec is None or module_spec.loader is None:
            raise TargetError(f"cannot import {path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        # Resolve project-local modules the way `python -m` would.
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())
        try:
            module = importlib.import_module(module_part)
        except ImportError as e:
            raise TargetError(f"cannot import {module_part!r}: {e}") from None
    fn = getattr(module, attr, None)
    if not callable(fn):
        raise TargetError(f"{module_part!r} has no callable {attr!r}")

    def call(case_input: Any) -> TargetResult:
        return coerce_result(fn(case_input))

    return call


_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: str) -> str:
    """Replace ${NAME} with the environment value; a missing variable is an error, not ''."""

    def sub(m: re.Match[str]) -> str:
        if m.group(1) not in os.environ:
            raise TargetError(f"environment variable {m.group(1)} is not set")
        return os.environ[m.group(1)]

    return _ENV_REF.sub(sub, value)


def dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, list) and part.isdigit():
            data = data[int(part)]
        elif isinstance(data, dict) and part in data:
            data = data[part]
        else:
            raise KeyError(f"response has no {path!r}")
    return data


def _http_target(url: str, config: HttpTargetConfig) -> Target:
    try:
        import httpx
    except ImportError:  # pragma: no cover - depends on the environment
        raise TargetError("HTTP targets need httpx: pip install 'regressgate[http]'") from None
    # Resolve secrets once, up front, so a missing variable fails before the first call.
    headers = {k: expand_env(v) for k, v in config.headers.items()}
    client = httpx.Client(timeout=config.timeout_s, headers=headers)

    def call(case_input: Any) -> TargetResult:
        response = client.request(config.method, url, json={config.input_field: case_input})
        response.raise_for_status()
        body = response.json()
        output = dig(body, config.output_path)
        return TargetResult(
            output=output if isinstance(output, str) else str(output),
            citations=list(dig(body, config.citations_path)) if config.citations_path else [],
            retrieved=list(dig(body, config.retrieved_path)) if config.retrieved_path else [],
            cost_usd=float(dig(body, config.cost_path)) if config.cost_path else None,
        )

    return call
