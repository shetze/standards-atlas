from pathlib import Path

import yaml

from standards_atlas.adapters.atlasdata.semantic_annotation_writer import (
    AtlasDataSemanticAnnotationService,
)


def test_apply_semantic_annotations_writes_public_tags_and_profile(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\n\nstructure=(\n "2025 r1"\n)\n\n'
        "#---data---#\nTOC;abc;Example:2025 1;Requirement;r\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "annotations.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2.0",
                "semantic_profile": "functional-safety:1.0.0",
                "annotations": [
                    {
                        "reference": "Example:2025 1",
                        "primary_statement_function": "requirement",
                        "knowledge_kinds": ["process"],
                        "role_relation_types": ["responsible_for"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = AtlasDataSemanticAnnotationService().apply(source, manifest, write=True)
    updated = source.read_text(encoding="utf-8")
    assert result.updated_records == 1
    assert 'semanticProfile="functional-safety:1.0.0"' in updated
    assert ";SP-REQ,KK-PRC,RR-RSP\n" in updated
    assert "Requirement text" not in updated


def test_apply_semantic_annotations_rejects_unknown_reference(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\nstructure=(\n "2025 1"\n)\n'
        "#---data---#\nTOC;abc;Example:2025 1;One;u\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "annotations.yaml"
    manifest.write_text(
        'semantic_profile: "functional-safety:1.0.0"\n'
        'annotations:\n  - reference: "Example:2025 2"\n',
        encoding="utf-8",
    )
    try:
        AtlasDataSemanticAnnotationService().apply(source, manifest)
    except ValueError as exc:
        assert "not found in TOC" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_semantic_annotations_rejects_task_reference_as_profile(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\nstructure=(\n "2025 1"\n)\n'
        "#---data---#\nTOC;abc;Example:2025 1;One;u\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "annotations.yaml"
    manifest.write_text(
        'schema_version: "2.0"\n'
        'semantic_profile: "semantic-profile-classification:2.4.0"\n'
        'annotations:\n  - reference: "Example:2025 1"\n'
        "    primary_statement_function: requirement\n",
        encoding="utf-8",
    )

    try:
        AtlasDataSemanticAnnotationService().apply(source, manifest, write=True)
    except ValueError as exc:
        assert "Unsupported semantic profile" in str(exc)
    else:
        raise AssertionError("expected ValueError")
