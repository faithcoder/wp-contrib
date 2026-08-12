from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repository: str
    number: int
    url: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repository}"


@dataclass(frozen=True)
class Issue:
    ref: IssueRef
    title: str
    body: str
    labels: list[str]
    state: str


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True)
class ValidationResult:
    name: str
    result: CommandResult


@dataclass
class WorkflowState:
    repository: str
    issue_number: int
    issue_url: str
    workspace: str
    branch: str
    issue_title: str = ""
    workflow_status: str = "initialized"
    agent_status: str = "not_started"
    validation_status: str = "not_run"
    approval_status: str = "pending"
    agent_report: str = ""
    validations: list[dict[str, Any]] = field(default_factory=list)
    pull_request_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace)
