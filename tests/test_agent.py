import pytest

from wp_contrib.agent import AgentError, agent_command, build_prompt
from wp_contrib.config import AgentConfig
from wp_contrib.models import Issue, IssueRef


def test_prompt_is_compact_and_has_safety_constraints() -> None:
    issue = Issue(IssueRef("owner", "repo", 4, "https://github.com/owner/repo/issues/4"), "Bug", "Details", [], "OPEN")
    prompt = build_prompt(issue)
    assert "GitHub issue #4" in prompt
    assert "owner/repo" in prompt
    assert "Do not commit" in prompt
    assert "Do not push" in prompt
    assert "Details" in prompt


def test_codex_command_uses_workspace_sandbox() -> None:
    assert agent_command(AgentConfig(provider="codex"), "fix it") == [
        "codex", "exec", "--sandbox", "workspace-write", "fix it"
    ]


def test_custom_command_substitutes_prompt_without_shell() -> None:
    config = AgentConfig(provider="custom", command=["agent", "run", "{prompt}"])
    assert agent_command(config, "fix it") == ["agent", "run", "fix it"]


def test_custom_command_requires_prompt_placeholder() -> None:
    with pytest.raises(AgentError):
        agent_command(AgentConfig(provider="custom", command=["agent", "run"]), "fix it")
