from __future__ import annotations

import json
from pathlib import Path

from .commands import run_command
from .models import ValidationResult


def _json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_validation_commands(workspace: Path) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    composer = _json(workspace / "composer.json")
    scripts = composer.get("scripts", {}) if isinstance(composer.get("scripts", {}), dict) else {}
    for script in ("test", "lint"):
        if script in scripts:
            commands.append((f"composer {script}", ["composer", script]))
    if not any(name == "composer test" for name, _ in commands):
        if (workspace / "vendor/bin/phpunit").exists():
            commands.append(("PHPUnit", ["vendor/bin/phpunit"]))
        elif (workspace / "phpunit.xml").exists() or (workspace / "phpunit.xml.dist").exists():
            commands.append(("PHPUnit", ["vendor/bin/phpunit"]))
    if not any(name == "composer lint" for name, _ in commands):
        if (workspace / "vendor/bin/phpcs").exists():
            commands.append(("PHPCS", ["vendor/bin/phpcs"]))
        if (workspace / "vendor/bin/phpstan").exists():
            commands.append(("PHPStan", ["vendor/bin/phpstan", "analyse"]))
    package = _json(workspace / "package.json")
    npm_scripts = package.get("scripts", {}) if isinstance(package.get("scripts", {}), dict) else {}
    for script in ("test", "lint", "build"):
        if script in npm_scripts:
            commands.append((f"npm {script}", ["npm", "run", script]))
    return commands


def run_validations(workspace: Path, timeout: int) -> list[ValidationResult]:
    return [
        ValidationResult(name, run_command(command, cwd=workspace, timeout=timeout))
        for name, command in detect_validation_commands(workspace)
    ]
