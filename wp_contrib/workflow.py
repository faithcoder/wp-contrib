from __future__ import annotations

import logging
from pathlib import Path

from .agent import AgentError, run_agent
from .commands import run_command
from .config import Config
from .github import find_linked_pull_requests
from .models import Issue, ValidationResult, WorkflowState
from .repository import branch_name, create_branch, ensure_clean, ensure_workspace, inspect_repository
from .state import save_state
from .validator import run_validations


class WorkflowError(RuntimeError):
    pass


log = logging.getLogger("wp_contrib")


def serialize_validations(results: list[ValidationResult]) -> list[dict[str, object]]:
    return [{
        "name": item.name, "command": item.result.command, "returncode": item.result.returncode,
        "stdout": item.result.stdout, "stderr": item.result.stderr,
        "duration": item.result.duration, "timed_out": item.result.timed_out,
    } for item in results]


def validate_state(state: WorkflowState, config: Config) -> WorkflowState:
    results = run_validations(state.workspace_path, config.validation.timeout)
    state.validations = serialize_validations(results)
    state.validation_status = "passed" if all(item.result.succeeded for item in results) else "failed"
    state.workflow_status = "review" if state.validation_status == "passed" else "validation_failed"
    save_state(state)
    return state


def solve_issue(issue: Issue, config: Config) -> tuple[WorkflowState, list[dict[str, object]]]:
    linked_prs = find_linked_pull_requests(issue.ref)
    workspace = ensure_workspace(issue.ref, config.workspace_dir)
    ensure_clean(workspace)
    branch = branch_name(issue.ref.number, issue.title)
    create_branch(workspace, branch)
    files = inspect_repository(workspace)
    log.info("Repository prepared; detected instruction/tooling files: %s", ", ".join(p.name for p in files))
    state = WorkflowState(
        repository=issue.ref.full_name, issue_number=issue.ref.number, issue_url=issue.ref.url,
        issue_title=issue.title, workspace=str(workspace), branch=branch,
        workflow_status="agent_running", agent_status="running",
    )
    save_state(state)
    result = None
    last_error: AgentError | None = None
    for attempt in range(1, max(1, config.agent.max_attempts) + 1):
        try:
            result = run_agent(issue, workspace)
            break
        except AgentError as exc:
            last_error = exc
            log.warning("OpenCode attempt %s failed: %s", attempt, exc)
    if result is None:
        state.agent_status = "failed"
        state.workflow_status = "agent_failed"
        save_state(state)
        raise last_error or WorkflowError("OpenCode failed without an error message.")
    state.agent_report = result.stdout
    state.agent_status = "completed"
    state.workflow_status = "validating"
    save_state(state)
    return validate_state(state, config), linked_prs


def _must_succeed(command: list[str], cwd: Path | None = None, action: str = "Command") -> str:
    result = run_command(command, cwd=cwd, timeout=300)
    if not result.succeeded:
        raise WorkflowError(f"{action} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def publish(state: WorkflowState) -> str:
    if state.approval_status != "approved":
        raise WorkflowError("Publishing is blocked until explicit approval.")
    workspace = state.workspace_path
    status = _must_succeed(["git", "status", "--porcelain"], workspace, "Git status")
    if not status:
        raise WorkflowError("There are no changes to publish.")
    _must_succeed(["git", "add", "--all"], workspace, "Staging")
    _must_succeed(["git", "commit", "-m", f"Fix #{state.issue_number}: {state.issue_title}"], workspace, "Commit")
    login = _must_succeed(["gh", "api", "user", "--jq", ".login"], action="GitHub user lookup")
    _must_succeed(["gh", "repo", "fork", state.repository, "--clone=false"], action="Fork creation")
    remotes = _must_succeed(["git", "remote"], workspace, "Remote inspection").splitlines()
    if "upstream" not in remotes:
        _must_succeed(["git", "remote", "rename", "origin", "upstream"], workspace, "Remote rename")
    fork_url = f"https://github.com/{login}/{state.repository.split('/', 1)[1]}.git"
    remotes = _must_succeed(["git", "remote"], workspace, "Remote inspection").splitlines()
    if "origin" not in remotes:
        _must_succeed(["git", "remote", "add", "origin", fork_url], workspace, "Fork remote setup")
    _must_succeed(["git", "push", "--set-upstream", "origin", state.branch], workspace, "Push")
    changed = _must_succeed(["git", "show", "--stat", "--oneline", "HEAD"], workspace, "Change summary")
    tests = "\n".join(
        f"- `{ ' '.join(item['command']) }`: {'passed' if item['returncode'] == 0 else 'failed'}"
        for item in state.validations
    ) or "- No automated validation command was configured; manual review performed."
    base = _must_succeed(
        ["gh", "repo", "view", state.repository, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
        action="Default branch lookup",
    )
    body = f"""## Summary

Fixes the reported issue: {state.issue_title}.

## Changes

```
{changed}
```

## Testing

{tests}

Fixes #{state.issue_number}
"""
    url = _must_succeed([
        "gh", "pr", "create", "--repo", state.repository, "--head", f"{login}:{state.branch}",
        "--base", base, "--title", f"Fix #{state.issue_number}: {state.issue_title}", "--body", body,
    ], workspace, "Pull request creation")
    state.pull_request_url = url.splitlines()[-1]
    state.workflow_status = "pr_created"
    save_state(state)
    return state.pull_request_url
