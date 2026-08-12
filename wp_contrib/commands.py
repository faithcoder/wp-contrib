from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .models import CommandResult


def run_command(
    command: list[str], cwd: Path | None = None, timeout: int | None = None
) -> CommandResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            command, completed.returncode, completed.stdout, completed.stderr,
            time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(
            command, 124, stdout, stderr, time.monotonic() - started, True
        )
    except OSError as exc:
        return CommandResult(command, 127, "", str(exc), time.monotonic() - started)
