from pathlib import Path

import yaml

from standards_atlas.application.schema import SCHEMA_BASELINES, require_current_schema


def test_persistent_schema_baselines_are_explicit() -> None:
    assert SCHEMA_BASELINES["engineering-document"].current == 4
    assert SCHEMA_BASELINES["standards-manifest"].current == 2
    assert SCHEMA_BASELINES["qualification-matrix-manifest"].current == "1.5"


def test_packaged_ontology_and_structural_resources_declare_schema_version() -> None:
    roots = (
        Path("src/standards_atlas/resources/semantic/tasks"),
        Path("src/standards_atlas/resources/ontologies"),
        Path("src/standards_atlas/resources/structure-taxonomies"),
    )
    for root in roots:
        for path in root.rglob("*.yaml"):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert payload["schema_version"] == 1, path


def test_current_baseline_rejects_previous_versions_during_cleanup_phase() -> None:
    try:
        require_current_schema("engineering-document", 2)
    except ValueError as exc:
        assert "writers may only emit current schema 4" in str(exc)
    else:
        raise AssertionError("old schema version unexpectedly accepted")
