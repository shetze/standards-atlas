from pathlib import Path

import pytest
import yaml

from standards_atlas.adapters.gemara import GemaraGuidanceExporter, GemaraGuidanceMapper
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


def _clause(
    identifier: str,
    reference: str,
    heading: str,
    *,
    text: str = "",
    parent: str | None = None,
    clause_type: ClauseType = ClauseType.CLAUSE,
) -> Clause:
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=clause_type,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"text-{identifier}", text=text),) if text else (),
    )


def _document() -> PublicationDocument:
    engineering = EngineeringDocument(
        key=DocumentKey(value="SAMPLE-1"),
        title="Sample Standard - Part 1",
        document_type=DocumentType.STANDARD,
        year=2026,
        version="2026-09",
        source="sample-source",
        clauses=(
            _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
            _clause("section-4", "4", "Requirements", parent="root"),
            _clause(
                "req-4-1",
                "4.1",
                "Design requirements",
                parent="section-4",
                text="The system shall provide deterministic behavior.",
                clause_type=ClauseType.REQUIREMENT,
            ),
        ),
    )
    return PublicationDocument.from_engineering_document(engineering)


def test_maps_document_to_guidance_catalog_with_structural_group() -> None:
    catalog = GemaraGuidanceMapper(gemara_version="v-test").map(_document())

    assert catalog.metadata.gemara_version == "v-test"
    assert catalog.metadata.version == "2026-09"
    assert catalog.metadata.author.id == "standards-atlas"
    assert [group.id for group in catalog.groups] == ["sample-1-root", "section-4"]
    assert len(catalog.guidelines) == 1
    assert catalog.guidelines[0].id == "req-4-1"
    assert catalog.guidelines[0].group == "section-4"
    assert catalog.guidelines[0].objective == "The system shall provide deterministic behavior."


def test_export_is_byte_deterministic_and_matches_golden_fixture(tmp_path: Path) -> None:
    exporter = GemaraGuidanceExporter(GemaraGuidanceMapper(gemara_version="v-test"))
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    exporter.export_document(_document(), first)
    exporter.export_document(_document(), second)

    assert first.read_bytes() == second.read_bytes()
    golden = Path("tests/fixtures/gemara/sample-guidance.yaml")
    assert first.read_text(encoding="utf-8") == golden.read_text(encoding="utf-8")
    payload = yaml.safe_load(first.read_text(encoding="utf-8"))
    assert payload["metadata"]["type"] == "GuidanceCatalog"
    assert payload["metadata"]["gemara-version"] == "v-test"
    assert payload["type"] == "Standard"
    assert payload["guidelines"][0]["state"] == "Active"
    assert "recommendations" not in payload["guidelines"][0]


def test_heading_only_leaf_is_not_invented_as_guidance() -> None:
    document = _document().model_copy(
        update={
            "clauses": _document().clauses + (_clause("empty", "5", "Heading only", parent="root"),)
        }
    )

    catalog = GemaraGuidanceMapper().map(document)

    assert "empty" not in {guideline.id for guideline in catalog.guidelines}


def test_rejects_identifier_collisions_after_normalization() -> None:
    document = _document().model_copy(
        update={
            "clauses": (
                _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
                _clause("section/4", "4", "Requirements A", parent="root"),
                _clause("section 4", "5", "Requirements B", parent="root"),
                _clause("req-a", "4.1", "A", parent="section/4", text="Requirement A."),
                _clause("req-b", "5.1", "B", parent="section 4", text="Requirement B."),
            )
        }
    )

    with pytest.raises(ValueError, match="group id collision"):
        GemaraGuidanceMapper().map(document)
