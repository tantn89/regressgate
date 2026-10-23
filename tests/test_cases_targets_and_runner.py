from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from regressgate.case_schema import Case, CaseFileError, load_cases
from regressgate.checks import CheckConfigError
from regressgate.run_report import RunReport
from regressgate.runner import run_suite
from regressgate.target_result import TargetResult, coerce_result
from regressgate.targets import HttpTargetConfig, TargetError, load_target


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def case(cid: str, **check: Any) -> Case:
    return Case(id=cid, input=cid, checks=[check or {"type": "contains", "terms": ["ok"]}])


# ---- case files ----------------------------------------------------------------------


def test_load_jsonl_and_yaml(tmp_path: Path) -> None:
    jsonl = write(tmp_path / "c.jsonl", "\n".join([
        json.dumps({"id": "a", "input": "q", "checks": [{"type": "contains", "terms": ["x"]}]}),
        "// a comment line",
        "",
        json.dumps({"id": "b", "input": {"q": 1}, "checks": [{"type": "regex", "pattern": "x"}]}),
    ]))
    assert [c.id for c in load_cases(jsonl)] == ["a", "b"]
    yaml_file = write(tmp_path / "c.yaml", "- id: a\n  input: q\n  checks:\n    - type: abstain\n")
    assert load_cases(yaml_file)[0].checks[0].type == "abstain"


@pytest.mark.parametrize(("content", "message"), [
    ('{"id": "a", "input": "q", "checks": []}', "line 1"),
    ("not json", "invalid JSON"),
    ('{"id": "a", "input": "q", "checks": [{"type": "x"}]}\n'
     '{"id": "a", "input": "q", "checks": [{"type": "x"}]}', "duplicate"),
    ("", "no cases"),
])
def test_bad_case_files_name_the_problem(tmp_path: Path, content: str, message: str) -> None:
    with pytest.raises(CaseFileError, match=message):
        load_cases(write(tmp_path / "c.jsonl", content))
    with pytest.raises(CaseFileError, match="not found"):
        load_cases(tmp_path / "missing.jsonl")
    with pytest.raises(CaseFileError, match="YAML list"):
        load_cases(write(tmp_path / "c.yaml", "id: a"))


def test_repeated_check_types_get_unique_labels() -> None:
    c = Case(id="a", input="q", checks=[{"type": "number", "value": 1, "abs_tol": 0},
                                        {"type": "number", "value": 2, "abs_tol": 0},
                                        {"type": "contains", "name": "mentions", "terms": ["x"]}])
    assert c.check_labels() == ["number", "number#2", "mentions"]


# ---- targets -------------------------------------------------------------------------


def test_coerce_result() -> None:
    assert coerce_result("hi").output == "hi"
    r = coerce_result({"output": "hi", "cost_usd": 0.1, "trace_id": "t1"})
    assert r.cost_usd == 0.1 and r.metadata == {"trace_id": "t1"}
    with pytest.raises(TypeError):
        coerce_result({"answer": "hi"})
    with pytest.raises(TypeError):
        coerce_result({"output": 3})
    with pytest.raises(TypeError):
        coerce_result(42)


def test_python_targets_by_module_and_by_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path / "my_target.py", "def answer(q):\n    return {'output': q.upper()}\n")
    monkeypatch.chdir(tmp_path)
    assert load_target("my_target:answer")("ok").output == "OK"
    assert load_target(f"{tmp_path / 'my_target.py'}:answer")("ok").output == "OK"
    for bad in ("no_colon", "my_target:missing", "no_such_module:fn", "missing.py:fn"):
        with pytest.raises(TargetError):
            load_target(bad)


@respx.mock
def test_http_target_maps_response_fields_and_expands_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RG_TOKEN", "secret-value")
    route = respx.post("https://api.example.com/ask").mock(return_value=httpx.Response(200, json={
        "data": {"answer": "Paris", "sources": [{"id": "s1"}], "usage": {"cost": 0.002}}}))
    config = HttpTargetConfig(
        input_field="question", headers={"Authorization": "Bearer ${RG_TOKEN}"},
        output_path="data.answer", citations_path="data.sources", cost_path="data.usage.cost",
    )
    result = load_target("https://api.example.com/ask", config)("capital of France?")
    assert result.output == "Paris" and result.citations == [{"id": "s1"}]
    assert result.cost_usd == 0.002
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer secret-value"
    assert json.loads(request.content) == {"question": "capital of France?"}


def test_http_target_missing_env_fails_before_any_call() -> None:
    with pytest.raises(TargetError, match="NOT_SET_ANYWHERE"):
        load_target("https://x.test", HttpTargetConfig(headers={"A": "${NOT_SET_ANYWHERE}"}))


# ---- runner --------------------------------------------------------------------------


def test_run_suite_repeats_grades_and_records_errors(tmp_path: Path) -> None:
    calls: list[str] = []
    lock = threading.Lock()

    def target(q: Any) -> TargetResult:
        with lock:
            calls.append(q)
        if q == "boom":
            raise RuntimeError("upstream 500")
        return TargetResult(output="ok" if q == "good" else "nope", cost_usd=0.01,
                            metadata={"trace": q})

    report = run_suite([case("good"), case("bad"), case("boom")], target, repeats=3,
                       concurrency=3, target_name="t")
    assert len(calls) == 9
    by_id = {c.id: c for c in report.cases}
    assert by_id["good"].pass_rate == 1 and by_id["bad"].pass_rate == 0
    assert by_id["boom"].trials[0].error == "RuntimeError: upstream 500"
    assert report.pass_rate == pytest.approx(1 / 3)
    assert report.mean_cost_usd() == pytest.approx(0.01)
    assert report.check_pass_rates() == {"contains": 0.5}
    assert by_id["good"].trials[0].metadata == {"trace": "good"}
    # Reports round-trip through JSON.
    path = report.save(tmp_path / "r" / "report.json")
    assert RunReport.load(path).model_dump() == report.model_dump()


def test_invalid_checks_abort_before_the_target_is_called() -> None:
    called = False

    def target(q: Any) -> str:
        nonlocal called
        called = True
        return "x"

    with pytest.raises(CheckConfigError, match="unknown check"):
        run_suite([case("a", type="nope")], lambda q: TargetResult(output=target(q)))
    assert not called
    with pytest.raises(CheckConfigError, match="case 'a'"):
        run_suite([case("a", type="number", value=1)], lambda q: TargetResult(output="1"))
    with pytest.raises(ValueError):
        run_suite([case("a")], lambda q: TargetResult(output="ok"), repeats=0)


def test_report_schema_version_is_enforced(tmp_path: Path) -> None:
    report = run_suite([case("a")], lambda q: TargetResult(output="ok"))
    data = json.loads(report.model_dump_json())
    data["schema_version"] = 99
    with pytest.raises(ValueError, match="schema v99"):
        RunReport.load(write(tmp_path / "r.json", json.dumps(data)))
