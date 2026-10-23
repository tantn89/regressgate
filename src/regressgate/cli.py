"""Command line: `regressgate run`, `regressgate compare`, `regressgate summary`.

Exit codes: 0 = pass / improvement / warn, 1 = the gate failed, 2 = usage or config error.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from regressgate.case_schema import CaseFileError, load_cases
from regressgate.checks import CheckConfigError
from regressgate.gate import compare_reports
from regressgate.markdown_report import render_gate, render_run
from regressgate.run_report import RunReport
from regressgate.runner import run_suite
from regressgate.suite_config import load_config
from regressgate.targets import TargetError, load_target

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Statistically sound regression gates for LLM, RAG and agent evals.")

ConfigOpt = Annotated[
    Path | None, typer.Option("--config", "-c", help="Suite config (default ./regressgate.yaml).")
]


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(2)


def _write(text: str, path: Path | None) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")


@app.command()
def run(
    config_path: ConfigOpt = None,
    target: Annotated[str | None, typer.Option(help="module:function or URL.")] = None,
    cases: Annotated[Path | None, typer.Option(help="JSONL or YAML case file.")] = None,
    repeats: Annotated[int | None, typer.Option(min=1, help="Trials per case.")] = None,
    concurrency: Annotated[int | None, typer.Option(min=1)] = None,
    out: Annotated[Path, typer.Option(help="Report JSON path.")] = Path(".regressgate/report.json"),
    markdown: Annotated[Path | None, typer.Option(help="Also write the summary here.")] = None,
) -> None:
    """Run every case against the target and save a JSON report."""
    config = load_config(config_path)
    # Flags are relative to the working directory; config values to the config file.
    target_spec = target or config.target_spec()
    cases_path = cases or config.cases_path()
    if not target_spec or not cases_path:
        raise _fail("set target and cases in regressgate.yaml or with --target / --cases")
    interactive = sys.stderr.isatty()

    def progress(done: int, total: int) -> None:
        if interactive:
            typer.echo(f"\r{done}/{total} trials", nl=False, err=True)

    try:
        suite = load_cases(cases_path)
        fn = load_target(target_spec, config.http)
        report = run_suite(
            suite, fn, target_name=target or config.target or "",
            repeats=repeats or config.repeats,
            concurrency=concurrency or config.concurrency,
            keep_outputs=config.keep_outputs,
            on_progress=progress,
        )
    except (CaseFileError, CheckConfigError, TargetError) as e:
        raise _fail(str(e)) from None
    if interactive:
        typer.echo("", err=True)
    report.save(out)
    summary = render_run(report, seed=config.gate.seed)
    typer.echo(summary)
    _write(summary, markdown)
    typer.echo(f"\nReport: {out}", err=True)


@app.command()
def compare(
    base: Annotated[Path, typer.Argument(help="Baseline report JSON.")],
    head: Annotated[Path, typer.Argument(help="Candidate report JSON.")],
    config_path: ConfigOpt = None,
    markdown: Annotated[Path | None, typer.Option(help="Write the verdict here.")] = None,
) -> None:
    """Gate HEAD against BASE. Exits 1 when the gate fails."""
    config = load_config(config_path)
    try:
        result = compare_reports(RunReport.load(base), RunReport.load(head), config.gate)
    except (OSError, ValueError) as e:
        raise _fail(str(e)) from None
    text = render_gate(result)
    typer.echo(text)
    _write(text, markdown)
    if result.failed:
        raise typer.Exit(1)


@app.command()
def summary(report: Annotated[Path, typer.Argument(help="Report JSON.")]) -> None:
    """Print the markdown summary of one report."""
    try:
        typer.echo(render_run(RunReport.load(report)))
    except (OSError, ValueError) as e:
        raise _fail(str(e)) from None


def main() -> None:  # pragma: no cover
    sys.exit(app())
