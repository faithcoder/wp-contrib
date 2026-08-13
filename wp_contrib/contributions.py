from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .commands import run_command


class ContributionsError(RuntimeError):
    pass


CACHE_FILE = Path(".wp-contrib-contributions.json")
PAGE_FILE = Path("CONTRIBUTIONS.md")


@dataclass
class Contribution:
    repository: str
    number: int
    title: str
    url: str
    state: str
    is_draft: bool
    review_decision: str
    checks: str
    feedback_count: int
    has_new_feedback: bool
    updated_at: str
    merged_at: str | None = None
    closed_at: str | None = None
    issues: list[dict[str, object]] = field(default_factory=list)

    @property
    def display_status(self) -> str:
        if self.merged_at:
            return "Merged"
        if self.state.upper() == "CLOSED":
            return "Closed"
        if self.is_draft:
            return "Draft"
        return "Open"

    @property
    def feedback(self) -> str:
        if self.has_new_feedback:
            return "New feedback"
        if self.review_decision == "CHANGES_REQUESTED":
            return "Changes requested"
        if self.review_decision == "APPROVED":
            return "Approved"
        return "None"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_contributions(path: Path = CACHE_FILE) -> list[Contribution]:
    raw = _read_json(path)
    if not isinstance(raw, list):
        return []
    try:
        return [Contribution(**item) for item in raw]
    except (TypeError, KeyError):
        return []


def save_contributions(items: list[Contribution], path: Path = CACHE_FILE) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps([asdict(item) for item in items], indent=2) + "\n")
    temporary.replace(path)


def _repository_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("nameWithOwner") or value.get("name") or "")
    return str(value)


def _checks_status(rollup: object) -> str:
    if not isinstance(rollup, list) or not rollup:
        return "Not configured"
    values: list[str] = []
    for check in rollup:
        if not isinstance(check, dict):
            continue
        value = check.get("conclusion") or check.get("state") or check.get("status") or ""
        values.append(str(value).upper())
    if any(value in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for value in values):
        return "Failing"
    if any(value in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED"} for value in values):
        return "Pending"
    if values and all(value in {"SUCCESS", "NEUTRAL", "SKIPPED"} for value in values):
        return "Passing"
    return "Unknown"


def _feedback_count(detail: dict[str, object], search: dict[str, object]) -> int:
    comments = detail.get("comments")
    reviews = detail.get("reviews")
    return (
        len(comments) if isinstance(comments, list) else int(search.get("commentsCount") or 0)
    ) + (len(reviews) if isinstance(reviews, list) else 0)


def _issues(detail: dict[str, object]) -> list[dict[str, object]]:
    references = detail.get("closingIssuesReferences")
    if not isinstance(references, list):
        return []
    issues: list[dict[str, object]] = []
    for reference in references:
        if not isinstance(reference, dict) or not reference.get("url") or not reference.get("number"):
            continue
        issues.append({
            "number": int(reference["number"]),
            "title": str(reference.get("title") or ""),
            "url": str(reference["url"]),
        })
    return issues


def refresh_contributions(limit: int = 100, cache_path: Path = CACHE_FILE) -> list[Contribution]:
    previous = {(item.repository, item.number): item for item in load_contributions(cache_path)}
    fields = "repository,number,title,url,state,isDraft,updatedAt,closedAt,commentsCount"
    search = run_command([
        "gh", "search", "prs", "--author", "@me", "--limit", str(limit),
        "--sort", "updated", "--order", "desc", "--json", fields,
    ], timeout=120)
    if not search.succeeded:
        raise ContributionsError(
            f"Could not refresh pull requests: {search.stderr.strip() or search.stdout.strip()}"
        )
    try:
        results = json.loads(search.stdout)
    except json.JSONDecodeError as exc:
        raise ContributionsError(f"GitHub CLI returned invalid PR search data: {exc}") from exc
    if not isinstance(results, list):
        raise ContributionsError("GitHub CLI returned unexpected PR search data.")
    items: list[Contribution] = []
    detail_fields = "state,isDraft,mergedAt,reviewDecision,statusCheckRollup,comments,reviews,closingIssuesReferences"
    for result in results:
        if not isinstance(result, dict):
            continue
        repository = _repository_name(result.get("repository"))
        number = int(result["number"])
        detail_result = run_command([
            "gh", "pr", "view", str(number), "--repo", repository, "--json", detail_fields,
        ], timeout=60)
        detail: dict[str, object] = {}
        if detail_result.succeeded:
            try:
                decoded = json.loads(detail_result.stdout)
                detail = decoded if isinstance(decoded, dict) else {}
            except json.JSONDecodeError:
                detail = {}
        count = _feedback_count(detail, result)
        old = previous.get((repository, number))
        items.append(Contribution(
            repository=repository,
            number=number,
            title=str(result.get("title") or ""),
            url=str(result.get("url") or ""),
            state=str(detail.get("state") or result.get("state") or "UNKNOWN"),
            is_draft=bool(detail.get("isDraft", result.get("isDraft", False))),
            review_decision=str(detail.get("reviewDecision") or ""),
            checks=_checks_status(detail.get("statusCheckRollup")),
            feedback_count=count,
            has_new_feedback=old is not None and count > old.feedback_count,
            updated_at=str(result.get("updatedAt") or ""),
            merged_at=str(detail["mergedAt"]) if detail.get("mergedAt") else None,
            closed_at=str(result["closedAt"]) if result.get("closedAt") else None,
            issues=_issues(detail),
        ))
    save_contributions(items, cache_path)
    return items


def contribution_stats(items: list[Contribution]) -> dict[str, int]:
    return {
        "total": len(items),
        "open": sum(item.display_status == "Open" for item in items),
        "draft": sum(item.display_status == "Draft" for item in items),
        "feedback": sum(item.feedback in {"New feedback", "Changes requested"} for item in items),
        "merged": sum(item.display_status == "Merged" for item in items),
        "closed": sum(item.display_status == "Closed" for item in items),
    }


def _date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return value


def render_markdown(items: list[Contribution]) -> str:
    stats = contribution_stats(items)
    lines = [
        "# Contribution Dashboard", "",
        "> Generated by `wp-contrib prs --refresh`. Do not edit manually.", "",
        "## Statistics", "",
        "| Total | Open | Draft | Needs attention | Merged | Closed |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {stats['total']} | {stats['open']} | {stats['draft']} | {stats['feedback']} | {stats['merged']} | {stats['closed']} |",
        "", "## Pull requests", "",
        "| Repository | Issue | PR | Title | Status | Review / feedback | Checks | Updated |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for item in items:
        title = item.title.replace("|", "\\|").replace("\n", " ")
        repository_url = f"https://github.com/{item.repository}"
        issue_links = ", ".join(
            f"[#{issue['number']}]({issue['url']})" for issue in item.issues
        ) or "—"
        lines.append(
            f"| [{item.repository}]({repository_url}) | {issue_links} | [#{item.number}]({item.url}) | {title} | "
            f"{item.display_status} | {item.feedback} | {item.checks} | {_date(item.updated_at)} |"
        )
    if not items:
        lines.append("| — | — | — | No contributions found | — | — | — | — |")
    return "\n".join(lines) + "\n"


def write_contributions_page(items: list[Contribution], path: Path = PAGE_FILE) -> None:
    path.write_text(render_markdown(items))
