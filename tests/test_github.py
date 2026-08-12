import pytest

from wp_contrib.github import GitHubError, parse_issue_url


def test_parse_issue_url() -> None:
    ref = parse_issue_url("https://github.com/WordPress/example-plugin/issues/123")
    assert (ref.owner, ref.repository, ref.number) == ("WordPress", "example-plugin", 123)


@pytest.mark.parametrize("url", [
    "http://github.com/a/b/issues/1", "https://gitlab.com/a/b/issues/1",
    "https://github.com/a/b/pull/1", "https://github.com/a/b/issues/nope",
    "https://github.com/a/b/issues/1?x=1",
])
def test_rejects_invalid_issue_urls(url: str) -> None:
    with pytest.raises(GitHubError):
        parse_issue_url(url)
