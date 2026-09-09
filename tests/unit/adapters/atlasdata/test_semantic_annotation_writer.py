from pathlib import Path

import pytest
import yaml

from standards_atlas.adapters.atlasdata.import_pipeline import AtlasDataImportPipeline
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


def _annotation_files(tmp_path: Path, annotation: dict, tags: str = "") -> tuple[Path, Path]:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\nsemanticProfile="functional-safety:1.0.0"\n'
        'structure=(\n "2025 r1"\n)\n#---data---#\n'
        f"TOC;abc;Example:2025 1;Requirement;r;{tags}\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "annotations.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2.0",
                "semantic_profile": "functional-safety:1.0.0",
                "annotations": [{"reference": "Example:2025 1", **annotation}],
            }
        ),
        encoding="utf-8",
    )
    return source, manifest


def test_applicability_tag_writer_importer_roundtrip_confirms_presence(tmp_path: Path) -> None:
    source, manifest = _annotation_files(tmp_path, {"applicability_functions": ["inclusion"]})
    AtlasDataSemanticAnnotationService().apply(source, manifest, write=True)
    document = AtlasDataImportPipeline().import_file(source)
    clause = next(c for c in document.clauses if c.reference.clause == "1")
    assert clause.enrichments.semantic.applicability_present is True
    assert clause.enrichments.semantic.applicability_functions == ("inclusion",)
    assert clause.provenance.protection("enrichments.semantic.applicability_present") == "confirmed"
    assert (
        clause.provenance.availability("enrichments.semantic.role_semantics_present")
        == "not_evaluated"
    )


def test_partial_annotation_merge_preserves_unaddressed_dimensions(tmp_path: Path) -> None:
    source, manifest = _annotation_files(
        tmp_path,
        {"primary_statement_function": "description"},
        "SP-REQ,KK-PRC,PF-ACT,RR-RSP",
    )
    original = source.read_bytes()
    service = AtlasDataSemanticAnnotationService()
    preview = service.apply(source, manifest, merge=True)
    assert preview.updated_records == 1
    assert source.read_bytes() == original
    service.apply(source, manifest, merge=True, write=True)
    assert ";SP-DES,KK-PRC,PF-ACT,RR-RSP\n" in source.read_text()
    second = source.read_bytes()
    service.apply(source, manifest, merge=True, write=True)
    assert source.read_bytes() == second


def test_explicit_empty_annotation_clears_only_addressed_namespace(tmp_path: Path) -> None:
    source, manifest = _annotation_files(tmp_path, {"knowledge_kinds": []}, "SP-REQ,KK-PRC,PF-ACT")
    AtlasDataSemanticAnnotationService().apply(source, manifest, merge=True, write=True)
    assert ";SP-REQ,PF-ACT\n" in source.read_text()


def test_default_annotation_replace_keeps_legacy_semantics(tmp_path: Path) -> None:
    source, manifest = _annotation_files(
        tmp_path,
        {"primary_statement_function": "description"},
        "SP-REQ,KK-PRC,PF-ACT",
    )
    AtlasDataSemanticAnnotationService().apply(source, manifest, write=True)
    assert ";SP-DES\n" in source.read_text()


def test_merge_rejects_profile_reinterpretation_without_writing(tmp_path: Path) -> None:
    source, manifest = _annotation_files(tmp_path, {"knowledge_kinds": []}, "SP-REQ")
    source.write_text(source.read_text().replace("functional-safety:1.0.0", "other:1.0.0"))
    original = source.read_bytes()
    with pytest.raises(ValueError, match="semanticProfile"):
        AtlasDataSemanticAnnotationService().apply(source, manifest, merge=True, write=True)
    assert source.read_bytes() == original


def test_duplicate_annotation_references_fail_before_writing(tmp_path: Path) -> None:
    source, manifest = _annotation_files(tmp_path, {"knowledge_kinds": []})
    payload = yaml.safe_load(manifest.read_text())
    payload["annotations"] *= 2
    manifest.write_text(yaml.safe_dump(payload))
    original = source.read_bytes()
    with pytest.raises(ValueError, match="must be unique"):
        AtlasDataSemanticAnnotationService().apply(source, manifest, write=True)
    assert source.read_bytes() == original
