from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class GithubConfig:
    use_gh_cli: bool = True


@dataclass(frozen=True)
class AgentConfig:
    provider: str = "opencode"
    max_attempts: int = 2


@dataclass(frozen=True)
class ValidationConfig:
    timeout: int = 300


@dataclass(frozen=True)
class WorkflowConfig:
    require_human_approval: bool = True


@dataclass(frozen=True)
class Config:
    workspace_dir: Path = Path("./workspaces")
    github: GithubConfig = field(default_factory=GithubConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)


def load_config(path: Path | None = None) -> Config:
    config_path = path or Path("config.yaml")
    if not config_path.exists():
        return Config()
    try:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read {config_path}: {exc}") from exc
    try:
        return Config(
            workspace_dir=Path(raw.get("workspace_dir", "./workspaces")).expanduser(),
            github=GithubConfig(**raw.get("github", {})),
            agent=AgentConfig(**raw.get("agent", {})),
            validation=ValidationConfig(**raw.get("validation", {})),
            workflow=WorkflowConfig(**raw.get("workflow", {})),
        )
    except TypeError as exc:
        raise ConfigError(f"Invalid setting in {config_path}: {exc}") from exc
