from __future__ import annotations

import re
from pathlib import Path

from .commands import run_command
from .models import Issue, IssueRef


class RepositoryError(RuntimeError):
    pass


INSTRUCTION_FILES = (
    "AGENTS.md", "CONTRIBUTING.md", "README.md", "composer.json", "package.json",
    "phpunit.xml", "phpunit.xml.dist", "phpcs.xml", "phpcs.xml.dist", "phpstan.neon",
)


def branch_name(number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48].rstrip("-")
    return f"fix/{number}-{slug or 'issue'}"


def _expected_remote(ref: IssueRef) -> str:
    return f"github.com/{ref.full_name.lower()}"


def ensure_workspace(ref: IssueRef, workspace_dir: Path) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    destination = workspace_dir / ref.repository
    if not destination.exists():
        result = run_command(["gh", "repo", "clone", ref.full_name, str(destination)])
        if not result.succeeded:
            raise RepositoryError(f"Clone failed: {result.stderr.strip() or result.stdout.strip()}")
    if not (destination / ".git").exists():
        raise RepositoryError(f"{destination} exists but is not a Git repository; it was left untouched.")
    remote = run_command(["git", "remote", "get-url", "origin"], cwd=destination)
    normalized = remote.stdout.strip().lower().removesuffix(".git").replace(":", "/")
    if not remote.succeeded or _expected_remote(ref) not in normalized:
        raise RepositoryError(
            f"Existing workspace {destination} does not have the expected origin {ref.full_name}."
        )
    return destination.resolve()


def ensure_clean(workspace: Path) -> None:
    result = run_command(["git", "status", "--porcelain"], cwd=workspace)
    if not result.succeeded:
        raise RepositoryError(f"Could not inspect Git status: {result.stderr.strip()}")
    if result.stdout.strip():
        raise RepositoryError(
            f"Workspace {workspace} has uncommitted changes. Commit or stash them before continuing."
        )


def create_branch(workspace: Path, name: str) -> None:
    existing = run_command(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"], cwd=workspace)
    if existing.returncode == 0:
        current = run_command(["git", "branch", "--show-current"], cwd=workspace)
        if current.stdout.strip() == name:
            return
        raise RepositoryError(f"Branch {name} already exists. Check it out or choose how to handle it manually.")
    result = run_command(["git", "switch", "-c", name], cwd=workspace)
    if not result.succeeded:
        raise RepositoryError(f"Could not create branch {name}: {result.stderr.strip()}")


def inspect_repository(workspace: Path) -> list[Path]:
    return [workspace / name for name in INSTRUCTION_FILES if (workspace / name).is_file()]
