"""regressgate: statistically sound regression gates for LLM, RAG and agent evals."""

from regressgate.case_schema import Case, CheckSpec, load_cases
from regressgate.checks import CheckOutcome, check
from regressgate.gate import GateConfig, GateResult, compare_reports
from regressgate.run_report import RunReport
from regressgate.runner import run_suite
from regressgate.target_result import TargetResult

__version__ = "0.1.0"

__all__ = [
    "Case",
    "CheckOutcome",
    "CheckSpec",
    "GateConfig",
    "GateResult",
    "RunReport",
    "TargetResult",
    "__version__",
    "check",
    "compare_reports",
    "load_cases",
    "run_suite",
]
