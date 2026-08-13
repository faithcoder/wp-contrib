from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

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
Progress = Callable[[str], None]


def _quiet(_: str) -> None:
    pass


def serialize_validations(results: list[ValidationResult]) -> list[dict[str, object]]:
    return [{
        "name": item.name, "command": item.result.command, "returncode": item.result.returncode,
        "stdout": item.result.stdout, "stderr": item.result.stderr,
        "duration": item.result.duration, "timed_out": item.result.timed_out,
    } for item in results]


def validate_state(
    state: WorkflowState, config: Config, progress: Progress = _quiet
) -> WorkflowState:
    progress("Detecting repository validation commands")
    results = run_validations(state.workspace_path, config.validation.timeout)
    state.validations = serialize_validations(results)
    state.validation_status = "passed" if all(item.result.succeeded for item in results) else "failed"
    state.workflow_status = "review" if state.validation_status == "passed" else "validation_failed"
    save_state(state)
    if not results:
        progress("No automated validation commands were configured")
    elif state.validation_status == "passed":
        progress(f"Validation passed ({len(results)} command(s))")
    else:
        progress(f"Validation failed ({len(results)} command(s)); review required")
    return state


def solve_issue(
    issue: Issue, config: Config, progress: Progress = _quiet
) -> tuple[WorkflowState, list[dict[str, object]]]:
    progress("Checking for existing pull requests that may address the issue")
    linked_prs = find_linked_pull_requests(issue.ref)
    progress("Preparing or verifying the local repository workspace")
    workspace = ensure_workspace(issue.ref, config.workspace_dir)
    progress("Checking that the repository has no uncommitted changes")
    ensure_clean(workspace)
    branch = branch_name(issue.ref.number, issue.title)
    progress(f"Creating or selecting branch {branch}")
    create_branch(workspace, branch)
    files = inspect_repository(workspace)
    detected = ", ".join(path.name for path in files) or "none"
    progress(f"Contribution and tooling files detected: {detected}")
    log.info("Repository prepared; detected instruction/tooling files: %s", ", ".join(p.name for p in files))
    state = WorkflowState(
        repository=issue.ref.full_name, issue_number=issue.ref.number, issue_url=issue.ref.url,
        issue_title=issue.title, workspace=str(workspace), branch=branch,
        workflow_status="agent_running", agent_status="running",
        agent_provider=config.agent.provider,
    )
    save_state(state)
    result = None
    last_error: AgentError | None = None
    for attempt in range(1, max(1, config.agent.max_attempts) + 1):
        try:
            progress(
                f"Calling {config.agent.provider} coding agent "
                f"(attempt {attempt}/{max(1, config.agent.max_attempts)}); this may take several minutes"
            )
            result = run_agent(issue, workspace, config.agent)
            progress(f"{config.agent.provider} coding agent finished")
            break
        except AgentError as exc:
            last_error = exc
            log.warning("Agent attempt %s failed: %s", attempt, exc)
    if result is None:
        state.agent_status = "failed"
        state.workflow_status = "agent_failed"
        save_state(state)
        raise last_error or WorkflowError("Coding agent failed without an error message.")
    state.agent_report = result.stdout
    state.agent_status = "completed"
    state.workflow_status = "validating"
    save_state(state)
    state = validate_state(state, config, progress)
    progress(
        "Changes are ready for human review"
        if state.validation_status == "passed"
        else "Changes require review because validation failed"
    )
    return state, linked_prs


def _must_succeed(command: list[str], cwd: Path | None = None, action: str = "Command") -> str:
    result = run_command(command, cwd=cwd, timeout=300)
    if not result.succeeded:
        raise WorkflowError(f"{action} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def find_pr_template(workspace: Path) -> Path | None:
    """Find a GitHub PR template using GitHub's standard locations."""
    preferred = (
        workspace / ".github" / "PULL_REQUEST_TEMPLATE.md",
        workspace / "PULL_REQUEST_TEMPLATE.md",
        workspace / "docs" / "PULL_REQUEST_TEMPLATE.md",
    )
    for expected in preferred:
        if expected.parent.is_dir():
            match = next(
                (path for path in expected.parent.iterdir() if path.is_file() and path.name.lower() == expected.name.lower()),
                None,
            )
            if match:
                return match
    directories = (workspace / ".github" / "PULL_REQUEST_TEMPLATE", workspace / "PULL_REQUEST_TEMPLATE")
    candidates = sorted(
        path for directory in directories if directory.is_dir()
        for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".md"
    )
    return candidates[0] if candidates else None


def _append_to_section(template: str, headings: set[str], content: str) -> tuple[str, bool]:
    pattern = re.compile(r"(?im)^(#{1,6})\s+(.+?)\s*$")
    matches = list(pattern.finditer(template))
    for index, match in enumerate(matches):
        normalized = re.sub(r"[^a-z]+", " ", match.group(2).lower()).strip()
        if normalized not in headings:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(template)
        return template[:end].rstrip() + f"\n\n{content}\n\n" + template[end:].lstrip(), True
    return template, False


def build_pr_body(state: WorkflowState, changed: str, tests: str, template: str = "") -> str:
    summary = f"Fixes the reported issue: {state.issue_title}."
    ai = (
        f"AI assistance: Yes\n\nTool(s): {state.agent_provider or 'coding agent'}\n\n"
        "Used for: Repository investigation, implementation, and test suggestions; "
        "the final diff and validation were reviewed by the contributor."
    )
    if not template.strip():
        return f"""## Summary

{summary}

## Changes

```
{changed}
```

## Testing

{tests}

## Use of AI Tools

{ai}

Fixes #{state.issue_number}
"""
    body = re.sub(
        r"(?im)^([ \t]*(?:fixes|closes|resolves)[ \t]+)#?(?:[ \t]*<!--[ \t]*#?issue(?:-number)?[ \t]*-->)?[ \t]*$",
        rf"\1#{state.issue_number}", template,
    )
    body, summary_added = _append_to_section(body, {"summary", "what", "description"}, summary)
    body, why_added = _append_to_section(
        body, {"why"}, f"Addresses the reported behavior in #{state.issue_number}."
    )
    body, changes_added = _append_to_section(body, {"changes", "how"}, f"```\n{changed}\n```")
    body, tests_added = _append_to_section(
        body, {"testing", "testing instructions", "tests"}, tests
    )
    body, ai_added = _append_to_section(body, {"use of ai tools", "ai disclosure"}, ai)
    additions: list[str] = []
    if not summary_added:
        additions += ["## Summary", summary]
    if not changes_added:
        additions += ["## Changes", f"```\n{changed}\n```"]
    if not tests_added:
        additions += ["## Testing", tests]
    if not ai_added:
        additions += ["## Use of AI Tools", ai]
    if not re.search(rf"(?im)\b(?:fixes|closes|resolves)\s+#?{state.issue_number}\b", body):
        additions.append(f"Fixes #{state.issue_number}")
    if additions:
        body = body.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    return body


def publish(state: WorkflowState, progress: Progress = _quiet) -> str:
    if state.approval_status != "approved":
        raise WorkflowError("Publishing is blocked until explicit approval.")
    workspace = state.workspace_path
    progress("Checking approved changes")
    status = _must_succeed(["git", "status", "--porcelain"], workspace, "Git status")
    if not status:
        raise WorkflowError("There are no changes to publish.")
    progress("Staging changes")
    _must_succeed(["git", "add", "--all"], workspace, "Staging")
    progress("Creating the local Git commit")
    _must_succeed(["git", "commit", "-m", f"Fix #{state.issue_number}: {state.issue_title}"], workspace, "Commit")
    progress("Identifying the authenticated GitHub account")
    login = _must_succeed(["gh", "api", "user", "--jq", ".login"], action="GitHub user lookup")
    progress("Creating or verifying the contributor fork")
    _must_succeed(["gh", "repo", "fork", state.repository, "--clone=false"], action="Fork creation")
    remotes = _must_succeed(["git", "remote"], workspace, "Remote inspection").splitlines()
    if "upstream" not in remotes:
        _must_succeed(["git", "remote", "rename", "origin", "upstream"], workspace, "Remote rename")
    fork_url = f"https://github.com/{login}/{state.repository.split('/', 1)[1]}.git"
    remotes = _must_succeed(["git", "remote"], workspace, "Remote inspection").splitlines()
    if "origin" not in remotes:
        _must_succeed(["git", "remote", "add", "origin", fork_url], workspace, "Fork remote setup")
    progress(f"Pushing branch {state.branch} to the contributor fork")
    _must_succeed(["git", "push", "--set-upstream", "origin", state.branch], workspace, "Push")
    if state.pull_request_url:
        state.workflow_status = "pr_updated"
        save_state(state)
        progress("Existing pull request updated")
        return state.pull_request_url
    changed = _must_succeed(["git", "show", "--stat", "--oneline", "HEAD"], workspace, "Change summary")
    tests = "\n".join(
        f"- `{ ' '.join(item['command']) }`: {'passed' if item['returncode'] == 0 else 'failed'}"
        for item in state.validations
    ) or "- No automated validation command was configured; manual review performed."
    base = _must_succeed(
        ["gh", "repo", "view", state.repository, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
        action="Default branch lookup",
    )
    template_path = find_pr_template(workspace)
    if template_path:
        progress(f"Using pull request template {template_path.relative_to(workspace)}")
    else:
        progress("No repository pull request template found; using the default body")
    template = template_path.read_text() if template_path else ""
    body = build_pr_body(state, changed, tests, template)
    progress("Creating the pull request on GitHub")
    url = _must_succeed([
        "gh", "pr", "create", "--repo", state.repository, "--head", f"{login}:{state.branch}",
        "--base", base, "--title", f"Fix #{state.issue_number}: {state.issue_title}", "--body", body,
    ], workspace, "Pull request creation")
    state.pull_request_url = url.splitlines()[-1]
    state.workflow_status = "pr_created"
    save_state(state)
    progress("Pull request is ready")
    return state.pull_request_url
