from pathlib import Path

import pytest
from typer.testing import CliRunner

from standards_atlas.cli.main import app

runner = CliRunner()


def _write_minimal_manifest(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "manifest_type: qualification_matrix",
                'schema_version: "1.3"',
                "matrix_id: matrix-v1",
                "corpus_id: corpus-v1",
                "task_version: 2.1.0",
                "dataset_version: 2.1.0",
                "prompts: []",
                "models: []",
                "reasoning_modes: []",
                "observations: []",
            )
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("flag", ["--no-cache", "--no-reuse", "--fresh"])
def test_recompute_rejects_freshness_controls(tmp_path: Path, flag: str) -> None:
    manifest = tmp_path / "matrix.yaml"
    _write_minimal_manifest(manifest)

    result = runner.invoke(
        app,
        [
            "evaluation",
            "qualification-matrix",
            "--manifest",
            str(manifest),
            "--recompute",
            flag,
        ],
    )

    assert result.exit_code == 2
    assert "cannot be combined" in result.output


@pytest.mark.parametrize("flag", ["--no-cache", "--no-reuse", "--fresh"])
def test_aggregate_only_rejects_freshness_controls(tmp_path: Path, flag: str) -> None:
    manifest = tmp_path / "matrix.yaml"
    _write_minimal_manifest(manifest)

    result = runner.invoke(
        app,
        [
            "evaluation",
            "qualification-matrix",
            "--manifest",
            str(manifest),
            "--aggregate-only",
            flag,
        ],
    )

    assert result.exit_code == 2
    assert "cannot be combined" in result.output
