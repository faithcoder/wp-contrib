from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .commands import run_command
from .models import Issue, IssueRef


class GitHubError(RuntimeError):
    pass


_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_issue_url(url: str) -> IssueRef:
    parsed = urlparse(url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    valid = (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower() == "github.com"
        and len(parts) == 4
        and parts[2] == "issues"
        and parts[3].isdigit()
        and int(parts[3]) > 0
        and all(_PART_RE.fullmatch(part) for part in parts[:2])
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise GitHubError(
            "Invalid issue URL. Expected https://github.com/OWNER/REPOSITORY/issues/123"
        )
    owner, repository = parts[:2]
    canonical = f"https://github.com/{owner}/{repository}/issues/{int(parts[3])}"
    return IssueRef(owner, repository, int(parts[3]), canonical)


def fetch_issue(ref: IssueRef) -> Issue:
    fields = "number,title,body,labels,state,url"
    result = run_command(
        ["gh", "issue", "view", str(ref.number), "--repo", ref.full_name, "--json", fields]
    )
    if not result.succeeded:
        message = result.stderr.strip() or result.stdout.strip()
        raise GitHubError(
            f"Could not retrieve {ref.url} with gh. Run 'gh auth status' and verify access. {message}"
        )
    try:
        data = json.loads(result.stdout)
        labels = [item["name"] for item in data.get("labels", [])]
        return Issue(ref, data["title"], data.get("body") or "", labels, data["state"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GitHubError(f"GitHub CLI returned unexpected issue data: {exc}") from exc


def find_linked_pull_requests(ref: IssueRef) -> list[dict[str, object]]:
    query = f"repo:{ref.full_name} is:pr is:open #{ref.number}"
    result = run_command(
        ["gh", "search", "prs", query, "--json", "number,title,url", "--limit", "10"]
    )
    if not result.succeeded:
        return []
    try:
        value = json.loads(result.stdout)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []
