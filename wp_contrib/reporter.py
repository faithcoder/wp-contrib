from __future__ import annotations

from .commands import run_command
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
