from wp_contrib.repository import branch_name, inspect_repository


def test_branch_name_is_sanitized() -> None:
    assert branch_name(123, "Fix PHP Warning: Don't Crash!") == "fix/123-fix-php-warning-don-t-crash"


def test_branch_name_has_fallback() -> None:
    assert branch_name(7, "🔥") == "fix/7-issue"


def test_inspect_repository(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("instructions")
    (tmp_path / "random.txt").write_text("ignore")
    assert [p.name for p in inspect_repository(tmp_path)] == ["AGENTS.md"]
