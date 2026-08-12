from wp_contrib.agent import build_prompt
from wp_contrib.models import Issue, IssueRef


def test_prompt_is_compact_and_has_safety_constraints() -> None:
    issue = Issue(IssueRef("owner", "repo", 4, "https://github.com/owner/repo/issues/4"), "Bug", "Details", [], "OPEN")
    prompt = build_prompt(issue)
    assert "GitHub issue #4" in prompt
    assert "owner/repo" in prompt
    assert "Do not commit" in prompt
    assert "Do not push" in prompt
    assert "Details" in prompt
