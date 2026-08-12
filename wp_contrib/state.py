from __future__ import annotations

import json
import os
from pathlib import Path

from .models import WorkflowState


class StateError(RuntimeError):
    pass


STATE_FILE = Path(".wp-contrib-state.json")


def save_state(state: WorkflowState, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
    os.replace(temporary, path)


def load_state(path: Path = STATE_FILE) -> WorkflowState:
    if not path.exists():
        raise StateError("No active workflow. Run: wp-contrib solve ISSUE_URL")
    try:
        data = json.loads(path.read_text())
        return WorkflowState(**data)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise StateError(f"Could not read workflow state from {path}: {exc}") from exc
