from __future__ import annotations

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .commands import run_command
from .contributions import Contribution, contribution_stats
from .models import WorkflowState


def changed_files(state: WorkflowState) -> str:
    result = run_command(["git", "status", "--short"], cwd=state.workspace_path)
    return result.stdout.rstrip() if result.succeeded else f"Unable to read status: {result.stderr.strip()}"


def diff_stat(state: WorkflowState) -> str:
    result = run_command(["git", "diff", "--stat"], cwd=state.workspace_path)
    return result.stdout.rstrip() if result.succeeded else f"Unable to read diff: {result.stderr.strip()}"


def render_report(state: WorkflowState) -> str:
    lines = [
        "Issue", "─" * 40, f"Repository: {state.repository}",
        f"Issue: #{state.issue_number}", f"Title: {state.issue_title}", "",
        "Agent", "─" * 40, f"Status: {state.agent_status}", "",
        "Changes", "─" * 40, changed_files(state) or "No changes", "",
        "Validation", "─" * 40,
    ]
    if state.validations:
        for item in state.validations:
            status = "PASS" if item["returncode"] == 0 and not item.get("timed_out") else "FAIL"
            lines.append(f"{item['name']:<20} {status} ({item['duration']:.1f}s)")
            if status == "FAIL":
                detail = (str(item.get("stderr", "")).strip() or str(item.get("stdout", "")).strip())
                if detail:
                    lines.append(f"  {detail[-2000:]}")
    else:
        lines.append("No validation commands configured")
    lines += ["", "Git", "─" * 40, diff_stat(state) or "No diff", "", "Status", "─" * 40]
    lines.append("READY FOR HUMAN REVIEW" if state.validation_status == "passed" else "VALIDATION FAILED\n\nReview the failure before continuing.")
    return "\n".join(lines)


def print_contributions(items: list[Contribution], console: Console | None = None) -> None:
    output = console or Console()
    stats = contribution_stats(items)
    cards = [
        Panel(str(stats[key]), title=label, expand=True)
        for key, label in (
            ("total", "Total"), ("open", "Open"), ("draft", "Draft"),
            ("feedback", "Needs attention"), ("merged", "Merged"), ("closed", "Closed"),
        )
    ]
    output.print(Columns(cards, equal=True, expand=True))
    table = Table(title="Pull requests", expand=True, show_lines=False)
    table.add_column("Repository", style="cyan", no_wrap=True)
    table.add_column("PR", justify="right")
    table.add_column("Title", overflow="fold")
    table.add_column("Status")
    table.add_column("Review / feedback")
    table.add_column("Checks")
    table.add_column("Updated", no_wrap=True)
    for item in items:
        status_style = "green" if item.display_status == "Merged" else "yellow" if item.display_status in {"Open", "Draft"} else "dim"
        feedback_style = "bold red" if item.feedback in {"New feedback", "Changes requested"} else "green" if item.feedback == "Approved" else ""
        checks_style = "red" if item.checks == "Failing" else "yellow" if item.checks == "Pending" else "green" if item.checks == "Passing" else "dim"
        table.add_row(
            item.repository,
            f"[link={item.url}]#{item.number}[/link]",
            item.title,
            f"[{status_style}]{item.display_status}[/{status_style}]",
            f"[{feedback_style}]{item.feedback}[/{feedback_style}]" if feedback_style else item.feedback,
            f"[{checks_style}]{item.checks}[/{checks_style}]",
            item.updated_at[:10] or "—",
        )
    if not items:
        table.add_row("—", "—", "No contributions found", "—", "—", "—", "—")
    output.print(table)
