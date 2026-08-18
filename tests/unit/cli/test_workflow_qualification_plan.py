from typer.testing import CliRunner

from standards_atlas.cli.main import app

QUALIFICATION_MANIFEST = (
    "manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml"
)


def test_qualification_task_plan_omits_doorstop_and_docling_by_default() -> None:
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "plan",
            "--task",
            "qualification",
            "--manifest",
            "manifests/standards.yaml",
            "--family",
            "EN50716",
            "--qualification-manifest",
            QUALIFICATION_MANIFEST,
            "--knowledge-domain",
            "functional-safety",
            "--corpus-seed",
            "20260818",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "markdown" in result.output
    assert "corpus-build" in result.output
    assert "qualification-matrix" in result.output
    assert "doorstop" not in result.output
    assert "docling convert" not in result.output


def test_qualification_task_plan_can_regenerate_docling() -> None:
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "plan",
            "--task",
            "qualification",
            "--manifest",
            "manifests/standards.yaml",
            "--family",
            "EN50716",
            "--qualification-manifest",
            QUALIFICATION_MANIFEST,
            "--regenerate-docling",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "docling convert" in result.output
    assert "--overwrite" in result.output


def test_qualification_plan_command_is_removed() -> None:
    result = CliRunner().invoke(app, ["workflow", "qualification-plan", "--help"])

    assert result.exit_code != 0
    assert "No such command" in result.output
