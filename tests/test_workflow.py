from wp_contrib.models import CommandResult, ValidationResult
from wp_contrib.workflow import serialize_validations


def test_validation_serialization_preserves_command_output() -> None:
    result = CommandResult(["composer", "test"], 1, "output", "failure", 1.25)
    serialized = serialize_validations([ValidationResult("composer test", result)])
    assert serialized[0]["command"] == ["composer", "test"]
    assert serialized[0]["returncode"] == 1
    assert serialized[0]["stderr"] == "failure"
