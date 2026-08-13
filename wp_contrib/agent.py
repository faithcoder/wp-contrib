from __future__ import annotations

from pathlib import Path

from .commands import run_command
from .config import AgentConfig
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


def agent_command(config: AgentConfig, prompt: str) -> list[str]:
    provider = config.provider.lower().strip()
    if provider == "opencode":
        return ["opencode", "run", prompt]
    if provider == "codex":
        return ["codex", "exec", "--sandbox", "workspace-write", prompt]
    if provider == "custom":
        if not config.command or "{prompt}" not in config.command:
            raise AgentError(
                "A custom agent requires agent.command as an argument list containing {prompt}."
            )
        return [part.replace("{prompt}", prompt) for part in config.command]
    raise AgentError("Unsupported agent provider. Choose opencode, codex, or custom.")


def agent_executable(config: AgentConfig) -> str:
    if config.provider.lower().strip() == "custom":
        if not config.command:
            raise AgentError("A custom agent requires agent.command.")
        return config.command[0]
    if config.provider.lower().strip() in {"opencode", "codex"}:
        return config.provider.lower().strip()
    raise AgentError("Unsupported agent provider. Choose opencode, codex, or custom.")


def run_agent(
    issue: Issue, workspace: Path, config: AgentConfig, timeout: int = 1800
) -> CommandResult:
    result = run_command(agent_command(config, build_prompt(issue)), cwd=workspace, timeout=timeout)
    if not result.succeeded:
        detail = result.stderr.strip() or result.stdout.strip()
        if result.timed_out:
            detail = f"timed out after {timeout} seconds. {detail}"
        raise AgentError(f"{config.provider} agent failed: {detail}")
    return result
