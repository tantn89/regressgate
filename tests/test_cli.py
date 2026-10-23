from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import make_report
from regressgate.cli import app

runner = CliRunner()


@pytest.fixture
def suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "capitals_target.py").write_text(
        "ANSWERS = {'France': 'Paris', 'Japan': 'Tokyo'}\n"
        "def answer(country):\n"
        "    return ANSWERS.get(country, \"I don't know.\")\n", encoding="utf-8")
    cases = [
        {"id": "fr", "input": "France", "checks": [{"type": "equals", "value": "paris"}]},
        {"id": "jp", "input": "Japan", "checks": [{"type": "equals", "value": "tokyo"}]},
        {"id": "xx", "input": "Atlantis", "checks": [{"type": "abstain"}]},
        {"id": "de", "input": "Germany", "checks": [{"type": "equals", "value": "berlin"}]},
    ]
    (tmp_path / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases),
                                          encoding="utf-8")
    (tmp_path / "regressgate.yaml").write_text(
        "target: capitals_target:answer\ncases: cases.jsonl\nrepeats: 2\n"
        "gate:\n  permutations: 500\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_writes_report_and_summary(suite: Path) -> None:
    result = runner.invoke(app, ["run", "--markdown", "summary.md"])
    assert result.exit_code == 0, result.output
    report = json.loads((suite / ".regressgate" / "report.json").read_text(encoding="utf-8"))
    assert report["repeats"] == 2 and len(report["cases"]) == 4
    assert "75.0% pass rate" in result.output
    assert "`de`" in (suite / "summary.md").read_text(encoding="utf-8")


def test_run_flags_override_config(suite: Path) -> None:
    result = runner.invoke(app, ["run", "--repeats", "1", "--out", "one.json"])
    assert result.exit_code == 0, result.output
    assert json.loads((suite / "one.json").read_text(encoding="utf-8"))["repeats"] == 1


def test_compare_exit_codes(suite: Path) -> None:
    base = {f"c{i}": (5, 5) for i in range(10)}
    make_report(base).save(suite / "base.json")
    make_report(base).save(suite / "same.json")
    make_report(base | {"c0": (0, 5)}).save(suite / "broken.json")
    ok = runner.invoke(app, ["compare", "base.json", "same.json"])
    assert ok.exit_code == 0 and "PASS" in ok.output
    bad = runner.invoke(app, ["compare", "base.json", "broken.json", "--markdown", "gate.md"])
    assert bad.exit_code == 1 and "REGRESSION" in bad.output
    assert "REGRESSION" in (suite / "gate.md").read_text(encoding="utf-8")


def test_summary_command(suite: Path) -> None:
    make_report({"a": (1, 2)}).save(suite / "r.json")
    result = runner.invoke(app, ["summary", "r.json"])
    assert result.exit_code == 0 and "50.0% pass rate" in result.output


@pytest.mark.parametrize("args", [
    ["run", "--target", "nope_module:fn"],
    ["run", "--cases", "missing.jsonl"],
    ["compare", "missing.json", "missing.json"],
    ["summary", "missing.json"],
])
def test_usage_errors_exit_2(suite: Path, args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "error:" in result.output


def test_run_without_target_or_cases_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["run"]).exit_code == 2
