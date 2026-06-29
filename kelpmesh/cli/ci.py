"""kelpmesh ci — unified CI/CD command.

Runs the full slim-CI pipeline in one shot:
  1. Detect changed models via git diff against the base branch
  2. Compute the impact plan (changed models + their downstream)
  3. Run only the affected models (deferred against production state if --defer is set)
  4. Run tests for changed models
  5. Format a structured report
  6. Post the report as a PR/MR comment on GitHub, GitLab, or Bitbucket
     (auto-detected from CI environment variables)

Usage in GitHub Actions:

    - name: KelpMesh CI
      run: kelpmesh ci
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

Usage in GitLab CI:

    kelpmesh-ci:
      script: kelpmesh ci
      variables:
        GITLAB_TOKEN: $CI_JOB_TOKEN

Exit codes: 0 = success, 1 = model or test failure, 2 = configuration error.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from kelpmesh.core.ci import _git_merge_base, changed_models

console = Console()
err_console = Console(stderr=True)

ci_app = typer.Typer(name="ci", help="CI/CD pipeline — slim run + tests + PR comment", invoke_without_command=True)


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class ModelRunResult:
    name: str
    status: str            # success | failed | skipped | deferred
    duration_s: float = 0.0
    materialized: str = ""
    error: str = ""


@dataclass
class TestRunResult:
    name: str
    status: str            # passed | failed | error
    model: str = ""
    error: str = ""


@dataclass
class CIReport:
    project:          str
    base_branch:      str
    sha:              str
    changed:          list[str]       # models directly modified
    planned:          list[str]       # changed + downstream
    run_results:      list[ModelRunResult]
    test_results:     list[TestRunResult]
    total_duration_s: float
    success:          bool
    dry_run:          bool
    errors:           list[str] = field(default_factory=list)

    @property
    def run_passed(self) -> int:
        return sum(1 for r in self.run_results if r.status == "success")

    @property
    def run_failed(self) -> int:
        return sum(1 for r in self.run_results if r.status == "failed")

    @property
    def run_skipped(self) -> int:
        return sum(1 for r in self.run_results if r.status in ("skipped", "deferred"))

    @property
    def test_passed(self) -> int:
        return sum(1 for t in self.test_results if t.status == "passed")

    @property
    def test_failed(self) -> int:
        return sum(1 for t in self.test_results if t.status in ("failed", "error"))


# ── Comment formatter ──────────────────────────────────────────────────────

def _fmt_comment(report: CIReport, run_url: str = "") -> str:
    run_ok   = report.run_failed == 0 and not report.dry_run
    test_ok  = report.test_failed == 0
    all_ok   = run_ok and test_ok

    status_emoji = "✅" if all_ok else "❌"
    title_parts  = []
    if report.planned:
        title_parts.append(f"{len(report.planned)} model{'s' if len(report.planned) != 1 else ''}")
    if report.test_results:
        title_parts.append(f"{len(report.test_results)} test{'s' if len(report.test_results) != 1 else ''}")
    title_parts.append(f"{report.total_duration_s:.1f}s")
    title_stats = " · ".join(title_parts)

    run_link = f" | [View run]({run_url})" if run_url else ""
    sha_str  = f"`{report.sha}`" if report.sha else ""
    branch_note = f"**Commit:** {sha_str}  " if sha_str else ""

    lines = [
        f"## {status_emoji} KelpMesh CI — {title_stats}{run_link}",
        "",
        f"{branch_note}**Changed:** {', '.join(f'`{m}`' for m in report.changed) if report.changed else '_none_'}",
        "",
        "---",
    ]

    # ── Plan ─────────────────────────────────────────────────────────────
    if report.planned:
        lines += [
            "",
            f"### 📊 Plan — {len(report.planned)} model{'s' if len(report.planned) != 1 else ''} queued",
            "",
            "| Model | Reason |",
            "|-------|--------|",
        ]
        for m in report.planned:
            reason = "🔄 modified" if m in report.changed else "⬆️ upstream changed"
            lines.append(f"| `{m}` | {reason} |")
    else:
        lines += ["", "### 📊 Plan — no models changed", ""]

    # ── Run ──────────────────────────────────────────────────────────────
    if not report.dry_run and report.run_results:
        run_icon = "✅" if run_ok else "❌"
        lines += [
            "",
            f"### {run_icon} Run — {report.run_passed}/{len(report.run_results)} succeeded",
            "",
            "| Model | Status | Duration |",
            "|-------|--------|----------|",
        ]
        for r in report.run_results:
            if r.status == "success":
                s = "✅ success"
            elif r.status == "failed":
                s = "❌ **failed**"
            elif r.status == "deferred":
                s = "⏭️ deferred"
            else:
                s = "⏭️ skipped"
            dur = f"{r.duration_s:.1f}s" if r.duration_s > 0 else "—"
            lines.append(f"| `{r.name}` | {s} | {dur} |")

        if report.run_skipped:
            lines.append("")
            lines.append(f"*{report.run_skipped} model(s) skipped or deferred to production state*")

        # Error details
        failures = [r for r in report.run_results if r.status == "failed" and r.error]
        if failures:
            lines += ["", "<details>", "<summary>Error details</summary>", ""]
            for r in failures:
                lines += [f"**`{r.name}`**", "```", r.error[:500], "```", ""]
            lines.append("</details>")

    elif report.dry_run:
        lines += ["", "### 🔍 Dry run — models not executed (--dry-run)", ""]

    # ── Tests ─────────────────────────────────────────────────────────────
    if report.test_results:
        test_icon   = "✅" if test_ok else "❌"
        test_label  = (
            f"{report.test_passed} passed · {report.test_failed} failed"
            if report.test_failed else f"{report.test_passed} passed"
        )
        lines += ["", f"### {test_icon} Tests — {test_label}", ""]

        failed_tests = [t for t in report.test_results if t.status in ("failed", "error")]
        passed_tests = [t for t in report.test_results if t.status == "passed"]

        if failed_tests:
            lines += ["| Test | Model | Status |", "|------|-------|--------|"]
            for t in failed_tests:
                lines.append(f"| `{t.name}` | `{t.model}` | ❌ {t.error[:80] if t.error else 'failed'} |")
            lines.append("")

        if passed_tests:
            summary = f"All {len(passed_tests)} tests passed" if not failed_tests else f"{len(passed_tests)} passing tests"
            lines += ["<details>", f"<summary>{summary}</summary>", ""]
            lines += ["| Test | Model | Status |", "|------|-------|--------|"]
            for t in passed_tests:
                lines.append(f"| `{t.name}` | `{t.model or '—'}` | ✅ |")
            lines += ["", "</details>"]

    # ── Footer ────────────────────────────────────────────────────────────
    lines += [
        "",
        "---",
        "<sub>🌿 KelpMesh v0.2.0 · [kelpmesh.io](https://kelpmesh.io) · "
        f"Base: `{report.base_branch}`</sub>",
    ]

    return "\n".join(lines)


# ── Core pipeline ──────────────────────────────────────────────────────────

def _run_pipeline(
    project_dir: Path,
    base_branch: Optional[str],
    defer: Optional[str],
    dry_run: bool,
    select: Optional[list[str]],
    full_refresh: bool,
) -> CIReport:
    t_start = time.time()

    # ── 1. Detect changes ────────────────────────────────────────────────
    base  = base_branch or _git_merge_base(project_dir)
    delta = changed_models(project_dir, base)

    # If --select is provided, override slim CI with explicit selection
    explicit_select = list(select) if select else None

    from kelpmesh.adapters import get_adapter
    from kelpmesh.core.executor import Executor
    from kelpmesh.core.project import Project
    from kelpmesh.state.engine import StateEngine

    try:
        project = Project(project_dir)
    except Exception as exc:
        return CIReport(
            project=str(project_dir), base_branch=base, sha=_get_sha(),
            changed=delta, planned=[], run_results=[], test_results=[],
            total_duration_s=0.0, success=False, dry_run=dry_run,
            errors=[f"Could not load project: {exc}"],
        )

    # ── 2. Compute plan (changed + downstream) ───────────────────────────
    if explicit_select:
        planned_names = _resolve_selection(project, explicit_select)
    elif delta:
        planned_names = _compute_plan(project, delta)
    else:
        planned_names = []

    run_results: list[ModelRunResult] = []
    test_results: list[TestRunResult] = []
    errors: list[str] = []
    success = True

    # ── 3. Run models ─────────────────────────────────────────────────────
    if not dry_run and planned_names:
        try:
            adapter = get_adapter(project.config.warehouse, project_path=str(project_dir))
            state   = StateEngine(project_dir)
            if full_refresh:
                state.reset()

            executor = Executor(
                project, adapter, state,
                defer_state_path=defer,
            )
            t_run = time.time()
            raw = executor.run(select=planned_names)
            run_duration = time.time() - t_run

            adapter.disconnect()
            state.close()

            run_results = _parse_run_results(raw, project, run_duration)
            if any(r.status == "failed" for r in run_results):
                success = False

        except Exception as exc:
            errors.append(f"Run error: {exc}")
            success = False

    # ── 4. Run tests ──────────────────────────────────────────────────────
    if not dry_run and not errors:
        try:
            test_results = _run_tests(project, project_dir, delta or planned_names)
            if any(t.status in ("failed", "error") for t in test_results):
                success = False
        except Exception as exc:
            errors.append(f"Test error: {exc}")

    return CIReport(
        project=project.config.name,
        base_branch=base,
        sha=_get_sha(),
        changed=delta,
        planned=planned_names,
        run_results=run_results,
        test_results=test_results,
        total_duration_s=time.time() - t_start,
        success=success,
        dry_run=dry_run,
        errors=errors,
    )


def _compute_plan(project, changed: list[str]) -> list[str]:
    """Return changed models + all downstream models, in topological order."""
    affected: set[str] = set(changed)
    for name in list(changed):
        # Walk downstream
        queue = [name]
        while queue:
            current = queue.pop(0)
            model = project.models.get(current)
            if model:
                for ds in model.downstream:
                    if ds not in affected:
                        affected.add(ds)
                        queue.append(ds)

    # Topological ordering from the project's model list
    topo = list(project.models.keys())
    return [m for m in topo if m in affected]


def _resolve_selection(project, select: list[str]) -> list[str]:
    result = []
    for name in select:
        if name.startswith("@"):
            name = name[1:]
            result.append(name)
            # include upstream
            model = project.models.get(name)
            if model:
                result.extend(list(model.upstream))
        else:
            result.append(name)
    seen, out = set(), []
    for n in result:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _parse_run_results(raw: dict, project, total_s: float) -> list[ModelRunResult]:
    results = []
    n_total  = len(raw.get("success", [])) + len(raw.get("failed", [])) + len(raw.get("skipped", []))
    per_model_s = total_s / max(n_total, 1)

    for name in raw.get("success", []):
        mat = project.models.get(name, None)
        results.append(ModelRunResult(
            name=name, status="success",
            duration_s=per_model_s,
            materialized=mat.materialized if mat else "",
        ))
    for item in raw.get("failed", []):
        name  = item if isinstance(item, str) else item.get("name", str(item))
        error = "" if isinstance(item, str) else str(item.get("error", ""))
        mat   = project.models.get(name, None)
        results.append(ModelRunResult(
            name=name, status="failed", duration_s=0.0,
            materialized=mat.materialized if mat else "",
            error=error,
        ))
    for name in raw.get("skipped", []):
        results.append(ModelRunResult(name=name, status="skipped"))
    for name in raw.get("deferred", []):
        results.append(ModelRunResult(name=name, status="deferred"))
    return results


def _run_tests(project, project_dir: Path, model_names: list[str]) -> list[TestRunResult]:
    from kelpmesh.adapters import get_adapter
    from kelpmesh.core.schema_yaml import SchemaYaml
    from kelpmesh.testing.runner import TestRunner
    from kelpmesh.testing.schema_tests import SchemaTestGenerator

    adapter = get_adapter(project.config.warehouse, project_path=str(project_dir))
    try:
        adapter.connect()
    except Exception:
        return []

    schema_yaml = SchemaYaml(project_dir)
    gen         = SchemaTestGenerator(schema_yaml)

    test_dir   = project_dir / "tests"
    test_files = []
    if test_dir.exists():
        all_files = list(test_dir.glob("*.sql"))
        if model_names:
            test_files = [f for f in all_files if any(m in f.stem for m in model_names)]
        else:
            test_files = all_files

    schema_tests = []
    for m in (model_names or list(project.models.keys())):
        model = project.models.get(m)
        if model:
            schema_tests.extend(gen.generate(m, model.name))

    runner = TestRunner(adapter, project_dir)
    try:
        report = runner.run_all(test_files=test_files, schema_tests=schema_tests or None)
    except Exception:
        adapter.disconnect()
        return []
    adapter.disconnect()

    results = []
    for r in report.results:
        model_name = ""
        for m in (model_names or []):
            if m in r.name:
                model_name = m
                break
        results.append(TestRunResult(
            name=r.name,
            status=r.status,
            model=model_name,
            error="; ".join(r.failures) if r.failures else (r.error or ""),
        ))
    return results


def _get_sha() -> str:
    sha = (
        os.environ.get("GITHUB_SHA")
        or os.environ.get("CI_COMMIT_SHA")
        or os.environ.get("BITBUCKET_COMMIT", "")
    )
    return sha[:7] if sha else ""


# ── Rich terminal output ────────────────────────────────────────────────────

def _print_report(report: CIReport):
    icon = "[green]✓[/green]" if report.success else "[red]✗[/red]"
    console.print(f"\n{icon} [bold]KelpMesh CI[/bold] — {report.project}  "
                  f"[dim]{report.total_duration_s:.1f}s[/dim]")

    if report.changed:
        console.print(f"  Changed models: [cyan]{', '.join(report.changed)}[/cyan]")
    else:
        console.print("  [dim]No model changes detected[/dim]")

    if report.planned:
        console.print(f"  Affected:       {len(report.planned)} model(s)")

    if not report.dry_run and report.run_results:
        t = Table(box=None, padding=(0, 1), show_header=False)
        t.add_column("icon",   width=3, no_wrap=True)
        t.add_column("name",   style="cyan", no_wrap=True)
        t.add_column("status", no_wrap=True)
        t.add_column("dur",    style="dim", justify="right")
        for r in report.run_results:
            if r.status == "success":
                icon, style = "✓", "green"
            elif r.status == "failed":
                icon, style = "✗", "red"
            else:
                icon, style = "–", "dim"
            dur = f"{r.duration_s:.1f}s" if r.duration_s else ""
            t.add_row(
                Text(icon, style=style),
                r.name,
                Text(r.status, style=style),
                dur,
            )
        console.print(t)

    if report.test_results:
        p = report.test_passed
        f = report.test_failed
        if f:
            console.print(f"  Tests: [green]{p} passed[/green]  [red]{f} failed[/red]")
        else:
            console.print(f"  Tests: [green]{p} passed[/green]")

    for err in report.errors:
        console.print(f"  [red]Error:[/red] {err}")


# ── Typer command ──────────────────────────────────────────────────────────

@ci_app.callback(invoke_without_command=True)
def ci_run(
    project_dir: Path = typer.Option(
        ".", "--project-dir", "-p", help="KelpMesh project root"
    ),
    base_branch: Optional[str] = typer.Option(
        None, "--base", "-b",
        help="Base branch/ref to diff against. Auto-detected (main/master) if omitted."
    ),
    defer: Optional[str] = typer.Option(
        None, "--defer", "-d",
        help="Path to production state DB — defer unchanged models to production."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan only — do not run models or tests."
    ),
    select: Optional[list[str]] = typer.Option(
        None, "--select", "-s", help="Explicit model selection (overrides slim CI)."
    ),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", help="Ignore incremental state and rebuild all selected models."
    ),
    post_comment: bool = typer.Option(
        True, "--post-comment/--no-comment",
        help="Post results as a PR/MR comment. Auto-detected from CI env vars."
    ),
    json_output: Optional[Path] = typer.Option(
        None, "--json-output", help="Write structured JSON report to this path."
    ),
    fail_on_test: bool = typer.Option(
        True, "--fail-on-test/--no-fail-on-test",
        help="Exit 1 when tests fail (default: true)."
    ),
):
    """Run slim CI: changed models → run → test → PR comment."""

    project_dir = project_dir.resolve()
    if not project_dir.exists():
        err_console.print(f"[red]Project directory not found: {project_dir}[/red]")
        raise typer.Exit(2)

    report = _run_pipeline(project_dir, base_branch, defer, dry_run, select, full_refresh)
    _print_report(report)

    # ── JSON output ──────────────────────────────────────────────────────
    if json_output:
        def _serial(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return asdict(obj)
            raise TypeError(type(obj))
        json_output.write_text(
            json.dumps(asdict(report), default=_serial, indent=2), encoding="utf-8"
        )
        console.print(f"  [dim]JSON report written to {json_output}[/dim]")

    # ── Post PR/MR comment ───────────────────────────────────────────────
    if post_comment:
        from kelpmesh.integrations import bitbucket as bb
        from kelpmesh.integrations import github as gh
        from kelpmesh.integrations import gitlab as gl

        ctx = gh.detect() or gl.detect() or bb.detect()
        if ctx:
            provider = (
                "GitHub"    if gh.detect() else
                "GitLab"    if gl.detect() else
                "Bitbucket"
            )
            run_url = ctx.get("run_url", "") or ctx.get("pipeline_url", "")
            body    = _fmt_comment(report, run_url)

            poster = gh.post_comment if provider == "GitHub" else (
                gl.post_comment if provider == "GitLab" else bb.post_comment
            )
            ok = poster(ctx, body)
            if ok:
                console.print(f"  [green]✓[/green] PR comment posted on {provider}")
            else:
                console.print(f"  [yellow]⚠[/yellow] Could not post comment on {provider}")
        else:
            console.print("  [dim]Not in a PR pipeline — skipping comment[/dim]")

    # ── Exit code ────────────────────────────────────────────────────────
    if not report.success:
        raise typer.Exit(1)
    if fail_on_test and report.test_failed > 0:
        raise typer.Exit(1)
