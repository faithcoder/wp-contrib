from wp_contrib.models import CommandResult, ValidationResult, WorkflowState
from wp_contrib.workflow import build_pr_body, find_pr_template, publish, serialize_validations


def test_validation_serialization_preserves_command_output() -> None:
    result = CommandResult(["composer", "test"], 1, "output", "failure", 1.25)
    serialized = serialize_validations([ValidationResult("composer test", result)])
    assert serialized[0]["command"] == ["composer", "test"]
    assert serialized[0]["returncode"] == 1
    assert serialized[0]["stderr"] == "failure"


def test_publish_updates_existing_pr_without_creating_another(monkeypatch, tmp_path) -> None:
    state = WorkflowState(
        "owner/repo", 12, "issue-url", str(tmp_path), "fix/12-bug",
        issue_title="Bug", approval_status="approved", pull_request_url="https://github.com/owner/repo/pull/99",
    )
    commands: list[list[str]] = []

    def fake_command(command, cwd=None, action="Command"):
        commands.append(command)
        if command[:3] == ["git", "status", "--porcelain"]:
            return " M file.php"
        if command == ["gh", "api", "user", "--jq", ".login"]:
            return "contributor"
        if command == ["git", "remote"]:
            return "origin\nupstream"
        return ""

    monkeypatch.setattr("wp_contrib.workflow._must_succeed", fake_command)
    monkeypatch.setattr("wp_contrib.workflow.save_state", lambda state: None)
    assert publish(state) == state.pull_request_url
    assert state.workflow_status == "pr_updated"
    assert not any(command[:3] == ["gh", "pr", "create"] for command in commands)


def test_publish_emits_progress(monkeypatch, tmp_path) -> None:
    state = WorkflowState(
        "owner/repo", 12, "issue-url", str(tmp_path), "fix/12-bug",
        issue_title="Bug", approval_status="approved", pull_request_url="https://example/pr/1",
    )

    def fake_command(command, cwd=None, action="Command"):
        if command[:3] == ["git", "status", "--porcelain"]:
            return " M file.php"
        if command == ["gh", "api", "user", "--jq", ".login"]:
            return "contributor"
        if command == ["git", "remote"]:
            return "origin\nupstream"
        return ""

    messages: list[str] = []
    monkeypatch.setattr("wp_contrib.workflow._must_succeed", fake_command)
    monkeypatch.setattr("wp_contrib.workflow.save_state", lambda state: None)
    publish(state, messages.append)
    assert "Staging changes" in messages
    assert "Existing pull request updated" in messages


def test_find_pr_template_is_case_insensitive(tmp_path) -> None:
    directory = tmp_path / ".github"
    directory.mkdir()
    template = directory / "pull_request_template.md"
    template.write_text("## What?\n")
    assert find_pr_template(tmp_path) == template


def test_find_pr_template_uses_sorted_named_template(tmp_path) -> None:
    directory = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE"
    directory.mkdir(parents=True)
    (directory / "feature.md").write_text("feature")
    expected = directory / "bug.md"
    expected.write_text("bug")
    assert find_pr_template(tmp_path) == expected


def test_build_pr_body_fills_common_template_sections() -> None:
    state = WorkflowState(
        "owner/repo", 42, "issue-url", "/tmp/repo", "fix/42-bug",
        issue_title="Broken options", agent_provider="codex",
    )
    template = """<!-- Keep this guidance -->
## What?
<!-- Describe it -->
Fixes #
## Why?
<!-- Explain -->
## How?
<!-- Explain -->
## Use of AI Tools
<!-- Disclose -->
## Testing Instructions
<!-- Test it -->
- [ ] I reviewed the changes
"""
    body = build_pr_body(state, "2 files changed", "- `composer test`: passed", template)
    assert "<!-- Keep this guidance -->" in body
    assert "Fixes #42" in body
    assert "Fixes the reported issue: Broken options." in body
    assert "Addresses the reported behavior in #42." in body
    assert "2 files changed" in body
    assert "Tool(s): codex" in body
    assert "`composer test`: passed" in body
    assert "- [ ] I reviewed the changes" in body


def test_build_pr_body_replaces_commented_issue_placeholder() -> None:
    state = WorkflowState("owner/repo", 454, "url", "/tmp/repo", "fix/454-x", issue_title="Bug")
    body = build_pr_body(state, "one file", "tests passed", "Closes <!-- #ISSUE-NUMBER -->")
    assert "Closes #454" in body
