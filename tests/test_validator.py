import json

from wp_contrib.validator import detect_validation_commands


def test_detects_declared_scripts(tmp_path) -> None:
    (tmp_path / "composer.json").write_text(json.dumps({"scripts": {"test": "phpunit", "lint": "phpcs"}}))
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest", "build": "wp-scripts build"}}))
    assert detect_validation_commands(tmp_path) == [
        ("composer test", ["composer", "test"]),
        ("composer lint", ["composer", "lint"]),
        ("npm test", ["npm", "run", "test"]),
        ("npm build", ["npm", "run", "build"]),
    ]


def test_does_not_invent_validation(tmp_path) -> None:
    assert detect_validation_commands(tmp_path) == []


def test_detects_phpunit_configuration(tmp_path) -> None:
    (tmp_path / "phpunit.xml.dist").write_text("<phpunit/>")
    assert detect_validation_commands(tmp_path) == [("PHPUnit", ["vendor/bin/phpunit"])]
