from __future__ import annotations

import logging
import shutil
import sys
import time

import typer

from .commands import run_command
from .contributions import (
    CACHE_FILE,
    PAGE_FILE,
    ContributionsError,
    load_contributions,
    refresh_contributions,
    write_contributions_page,
)
from .config import ConfigError, load_config
from .agent import AgentError, agent_executable
from .config import AgentConfig
from .github import GitHubError, fetch_issue, parse_issue_url
from .repository import RepositoryError
from .reporter import print_contributions, render_report
from .state import StateError, load_state, save_state
from .workflow import WorkflowError, publish, solve_issue, validate_state

app = typer.Typer(no_args_is_help=True, help="Automate a human-approved WordPress contribution workflow.")


def _configure_logging() -> None:
    logging.basicConfig(filename="wp-contrib.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _die(message: str) -> None:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _progress(message: str) -> None:
    typer.secho(f"  ✓ {message}", fg=typer.colors.CYAN)


def check_environment(agent: AgentConfig | None = None) -> None:
    required = {"git": "https://git-scm.com/downloads", "gh": "https://cli.github.com/"}
    if agent:
        executable = agent_executable(agent)
        install_url = (
            "https://developers.openai.com/codex/cli/" if executable == "codex"
            else "https://opencode.ai/docs/" if executable == "opencode"
            else "the documentation for your configured agent"
        )
        required[executable] = install_url
    missing = [(name, url) for name, url in required.items() if shutil.which(name) is None]
    if sys.version_info < (3, 11):
        missing.append(("Python 3.11+", "https://www.python.org/downloads/"))
    if missing:
        details = "; ".join(f"install {name}: {url}" for name, url in missing)
        _die(f"Missing prerequisites: {details}")
    auth = run_command(["gh", "auth", "status"])
    if not auth.succeeded:
        _die("GitHub CLI is not authenticated. Run: gh auth login")
    if agent and agent.provider.lower().strip() == "codex":
        codex_auth = run_command(["codex", "login", "status"])
        if not codex_auth.succeeded:
            _die("Codex CLI is not authenticated. Run: codex login")


@app.command()
def solve(issue_url: str) -> None:
    """Start or resume work on a GitHub issue."""
    try:
        _configure_logging()
        typer.secho("wp-contrib workflow", bold=True)
        config = load_config()
        _progress("Configuration loaded")
        ref = parse_issue_url(issue_url)
        _progress(f"Issue URL parsed: {ref.full_name}#{ref.number}")
        check_environment(config.agent)
        _progress("Git, GitHub CLI, authentication, and coding agent are ready")
        _progress("Retrieving issue details from GitHub")
        issue = fetch_issue(ref)
        _progress(f"Issue found: {issue.title}")
        if issue.state.upper() != "OPEN":
            _die(f"Issue #{ref.number} is {issue.state.lower()}; only open issues can be solved.")
        _progress("Issue is open")
        state, linked_prs = solve_issue(issue, config, _progress)
    except (ConfigError, GitHubError, RepositoryError, AgentError, WorkflowError) as exc:
        _die(str(exc))
    if linked_prs:
        typer.secho("Warning: open pull requests may address this issue:", fg=typer.colors.YELLOW)
        for pr in linked_prs:
            typer.echo(f"  #{pr.get('number')} {pr.get('title')} {pr.get('url')}")
    typer.echo(render_report(state))


@app.command()
def status() -> None:
    """Show the active workflow status."""
    try:
        typer.echo(render_report(load_state()))
    except StateError as exc:
        _die(str(exc))


@app.command("diff")
def show_diff() -> None:
    """Show the active workspace's Git diff."""
    try:
        state = load_state()
        result = run_command(["git", "diff", "--no-ext-diff"], cwd=state.workspace_path)
        if not result.succeeded:
            _die(result.stderr.strip())
        typer.echo(result.stdout, nl=False)
    except StateError as exc:
        _die(str(exc))


@app.command("test")
def test_command() -> None:
    """Run detected validation for the active workspace."""
    try:
        state = validate_state(load_state(), load_config(), _progress)
        typer.echo(render_report(state))
    except (StateError, ConfigError) as exc:
        _die(str(exc))


@app.command()
def approve() -> None:
    """Approve changes, then create or update the pull request."""
    try:
        state = load_state()
        typer.echo(render_report(state))
        typer.echo(f"\nBranch: {state.branch}")
        if state.validation_status != "passed":
            _die("Validation has not passed. Review failures and run 'wp-contrib test' again.")
        action = "update the existing PR" if state.pull_request_url else "create the PR"
        if not typer.confirm(f"Approve these changes, commit them, push to your fork, and {action}?", default=False):
            typer.echo("Not approved. Nothing was pushed.")
            raise typer.Exit()
        state.approval_status = "approved"
        save_state(state)
        typer.secho("\nPublishing workflow", bold=True)
        url = publish(state, _progress)
        verb = "updated" if state.workflow_status == "pr_updated" else "created"
        typer.echo(f"Pull request {verb}: {url}")
    except (StateError, WorkflowError) as exc:
        _die(str(exc))


@app.command()
def abort() -> None:
    """Mark the active workflow aborted without deleting work."""
    try:
        state = load_state()
        state.workflow_status = "aborted"
        state.approval_status = "rejected"
        save_state(state)
        typer.echo("Workflow marked aborted. Repository files and branch were not deleted.")
    except StateError as exc:
        _die(str(exc))


@app.command()
def prs(
    refresh: bool = typer.Option(False, "--refresh", help="Fetch current PR data from GitHub."),
    watch: bool = typer.Option(False, "--watch", help="Continuously refresh until Ctrl-C."),
    interval: int = typer.Option(300, "--interval", min=30, help="Watch refresh interval in seconds."),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum authored PRs to track."),
) -> None:
    """Show the contribution dashboard and generate CONTRIBUTIONS.md."""
    try:
        check_environment()
        first = True
        while True:
            cached = load_contributions()
            items = refresh_contributions(limit) if refresh or watch or not cached else cached
            write_contributions_page(items)
            if watch and not first:
                typer.clear()
            print_contributions(items)
            typer.echo(f"\nDashboard page: {PAGE_FILE.resolve()}")
            if not watch:
                if not refresh and cached:
                    typer.echo("Cached data shown. Run 'wp-contrib prs --refresh' for GitHub updates.")
                break
            typer.echo(f"Refreshing every {interval} seconds. Press Ctrl-C to stop.")
            first = False
            time.sleep(interval)
    except ContributionsError as exc:
        _die(str(exc))
    except KeyboardInterrupt:
        typer.echo("\nStopped watching pull requests.")
