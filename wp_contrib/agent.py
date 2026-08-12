from __future__ import annotations

from pathlib import Path

from .commands import run_command
from .models import CommandResult, Issue


class AgentError(RuntimeError):
    pass


def build_prompt(issue: Issue) -> str:
    return f"""You are fixing GitHub issue #{issue.ref.number}.

Title:
{issue.title}

Issue:
{issue.body}

Repository:
{issue.ref.full_name}

Instructions:

1. Read AGENTS.md and CONTRIBUTING.md if present.
2. Inspect the repository before making changes.
3. Investigate the reported problem.
4. Reproduce the issue when practical.
5. Determine the root cause.
6. Implement the smallest safe fix.
7. Avoid unrelated refactoring.
8. Add or update tests when appropriate.
9. Run relevant existing tests when practical.
10. Do not commit.
11. Do not push.
12. Do not create a pull request.

When finished, provide a concise report containing:

- root cause
- solution
- changed files
- tests performed
- tests that failed
- anything requiring human verification
"""


def run_agent(issue: Issue, workspace: Path, timeout: int = 1800) -> CommandResult:
    result = run_command(["opencode", "run", build_prompt(issue)], cwd=workspace, timeout=timeout)
    if not result.succeeded:
        detail = result.stderr.strip() or result.stdout.strip()
        if result.timed_out:
            detail = f"timed out after {timeout} seconds. {detail}"
        raise AgentError(f"OpenCode failed: {detail}")
    return result
