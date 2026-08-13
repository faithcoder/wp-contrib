from wp_contrib.models import CommandResult, ValidationResult, WorkflowState
from wp_contrib.workflow import publish, serialize_validations


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
