from pathlib import Path

import pytest

from standards_atlas.application.workflow import (
    WorkflowManifestLoader,
    WorkflowManifestType,
    parse_manifest_options,
)


def test_parse_manifest_options_flattens_repeated_and_comma_separated_values() -> None:
    assert parse_manifest_options(("a.yaml,b.yaml", "c.yaml")) == (
        Path("a.yaml"),
        Path("b.yaml"),
        Path("c.yaml"),
    )


def test_loader_resolves_manifest_types_independent_of_order(tmp_path: Path) -> None:
    standards = tmp_path / "standards.yaml"
    standards.write_text("manifest_type: standards\nschema_version: 2\n", encoding="utf-8")
    qualification = tmp_path / "qualification.yaml"
    qualification.write_text(
        "manifest_type: qualification_matrix\nschema_version: '1.5'\n",
        encoding="utf-8",
    )

    result = WorkflowManifestLoader().load((qualification, standards))

    assert result.require(WorkflowManifestType.STANDARDS) == standards
    assert result.require(WorkflowManifestType.QUALIFICATION_MATRIX) == qualification


def test_loader_rejects_duplicate_manifest_type(tmp_path: Path) -> None:
    first = tmp_path / "a.yaml"
    second = tmp_path / "b.yaml"
    for path in (first, second):
        path.write_text("manifest_type: standards\nschema_version: 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one manifest of type 'standards'"):
        WorkflowManifestLoader().load((first, second))


def test_loader_requires_common_headers(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema_version: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest_type"):
        WorkflowManifestLoader().load((manifest,))
