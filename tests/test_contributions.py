import json

from wp_contrib.contributions import (
    Contribution,
    contribution_stats,
    refresh_contributions,
    render_markdown,
)
from wp_contrib.models import CommandResult


def contribution(**overrides) -> Contribution:
    values = {
        "repository": "owner/repo", "number": 1, "title": "Fix bug", "url": "https://example/pr/1",
        "state": "OPEN", "is_draft": False, "review_decision": "", "checks": "Passing",
        "feedback_count": 0, "has_new_feedback": False, "updated_at": "2026-08-13T10:00:00Z",
    }
    values.update(overrides)
    return Contribution(**values)


def test_stats_classify_prs() -> None:
    items = [
        contribution(), contribution(number=2, is_draft=True),
        contribution(number=3, state="CLOSED", merged_at="2026-08-01T00:00:00Z"),
        contribution(number=4, review_decision="CHANGES_REQUESTED"),
    ]
    assert contribution_stats(items) == {
        "total": 4, "open": 2, "draft": 1, "feedback": 1, "merged": 1, "closed": 0,
    }


def test_markdown_has_stats_grid_and_list() -> None:
    page = render_markdown([contribution(issues=[{
        "number": 42, "title": "Reported bug", "url": "https://github.com/owner/repo/issues/42",
    }])])
    assert "| Total | Open | Draft | Needs attention | Merged | Closed |" in page
    assert "[#[" not in page
    assert "[#1](https://example/pr/1)" in page
    assert "[owner/repo](https://github.com/owner/repo)" in page
    assert "[#42](https://github.com/owner/repo/issues/42)" in page


def test_refresh_detects_new_feedback(monkeypatch, tmp_path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps([{**contribution(feedback_count=1).__dict__}]))
    search = [{
        "repository": {"nameWithOwner": "owner/repo"}, "number": 1, "title": "Fix bug",
        "url": "https://example/pr/1", "state": "open", "isDraft": False,
        "updatedAt": "2026-08-13T12:00:00Z", "closedAt": None, "commentsCount": 1,
    }]
    detail = {
        "state": "OPEN", "isDraft": False, "mergedAt": None, "reviewDecision": "CHANGES_REQUESTED",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}], "comments": [{}], "reviews": [{}],
        "closingIssuesReferences": [{
            "number": 42, "title": "Reported bug", "url": "https://github.com/owner/repo/issues/42",
        }],
    }
    responses = iter([
        CommandResult(["gh"], 0, json.dumps(search), "", 0.1),
        CommandResult(["gh"], 0, json.dumps(detail), "", 0.1),
    ])
    monkeypatch.setattr("wp_contrib.contributions.run_command", lambda *args, **kwargs: next(responses))
    items = refresh_contributions(cache_path=cache)
    assert items[0].has_new_feedback
    assert items[0].checks == "Passing"
    assert items[0].feedback == "New feedback"
    assert items[0].issues[0]["number"] == 42
