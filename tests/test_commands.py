import subprocess

from wp_contrib.commands import run_command


def test_command_result(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 3, "out", "err"))
    result = run_command(["fake"])
    assert result.returncode == 3
    assert result.stdout == "out"
    assert not result.succeeded
