"""The obsolete Run 074 must not reach canonical or public AtlasData writes."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from standards_atlas.cli import app


@pytest.mark.qualification
def test_run074_cli_rejection_creates_no_canonical_or_public_outputs(tmp_path) -> None:
    source = os.environ.get("STANDARDS_ATLAS_RUN074_ARCHIVE")
    if not source:
        pytest.skip("set STANDARDS_ATLAS_RUN074_ARCHIVE to the original obsolete private ZIP")
    output = tmp_path / "report.json"
    workspace = tmp_path / "canonical"
    result = CliRunner().invoke(
        app,
        [
            "document",
            "adopt-qualification",
            "--run",
            str(Path(source).resolve()),
            "--workspace",
            str(workspace),
            "--output",
            str(output),
            "--write",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "5.0" in result.output
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
