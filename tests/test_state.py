from wp_contrib.models import WorkflowState
from wp_contrib.state import load_state, save_state


def test_state_round_trip(tmp_path) -> None:
    path = tmp_path / "state.json"
    original = WorkflowState("owner/repo", 12, "url", "/tmp/repo", "fix/12-bug")
    save_state(original, path)
    assert load_state(path) == original


def test_state_save_replaces_existing(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = WorkflowState("a/b", 1, "url", "/tmp/x", "fix/1-x")
    save_state(state, path)
    state.workflow_status = "review"
    save_state(state, path)
    assert load_state(path).workflow_status == "review"
