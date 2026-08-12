from __future__ import annotations

import logging
import shutil
import sys

import typer

from .commands import run_command
from .config import ConfigError, load_config
from .agent import AgentError
from .github import GitHubError, fetch_issue, parse_issue_url
from .repository import RepositoryError
from .reporter import render_report
from .state import StateError, load_state, save_state
from .workflow import WorkflowError, publish, solve_issue, validate_state

app = typer.Typer(no_args_is_help=True, help="Automate a human-approved WordPress contribution workflow.")


def _configure_logging() -> None:
    logging.basicConfig(filename="wp-contrib.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _die(message: str) -> None:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def check_environment(require_agent: bool = True) -> None:
    required = {"git": "https://git-scm.com/downloads", "gh": "https://cli.github.com/"}
    if require_agent:
        required["opencode"] = "https://opencode.ai/docs/"
    missing = [(name, url) for name, url in required.items() if shutil.which(name) is None]
    if sys.version_info < (3, 11):
        missing.append(("Python 3.11+", "https://www.python.org/downloads/"))
    if missing:
        details = "; ".join(f"install {name}: {url}" for name, url in missing)
        _die(f"Missing prerequisites: {details}")
    auth = run_command(["gh", "auth", "status"])
    if not auth.succeeded:
        _die("GitHub CLI is not authenticated. Run: gh auth login")


@app.command()
def solve(issue_url: str) -> None:
    """Start or resume work on a GitHub issue."""
    try:
        _configure_logging()
        config = load_config()
        ref = parse_issue_url(issue_url)
        check_environment()
        issue = fetch_issue(ref)
        if issue.state.upper() != "OPEN":
            _die(f"Issue #{ref.number} is {issue.state.lower()}; only open issues can be solved.")
        state, linked_prs = solve_issue(issue, config)
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
        state = validate_state(load_state(), load_config())
        typer.echo(render_report(state))
    except (StateError, ConfigError) as exc:
        _die(str(exc))


@app.command()
def approve() -> None:
    """Review, approve, push, and create a pull request."""
    try:
        state = load_state()
        typer.echo(render_report(state))
        typer.echo(f"\nBranch: {state.branch}")
        if state.validation_status != "passed":
            _die("Validation has not passed. Review failures and run 'wp-contrib test' again.")
        if not typer.confirm("Approve these changes, commit them, push to your fork, and create the PR?", default=False):
            typer.echo("Not approved. Nothing was pushed.")
            raise typer.Exit()
        state.approval_status = "approved"
        save_state(state)
        typer.echo(f"Pull request created: {publish(state)}")
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
