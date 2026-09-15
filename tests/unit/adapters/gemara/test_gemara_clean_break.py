from standards_atlas.adapters.gemara import GemaraControlMapper
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    NormativeStatus,
    StandardReference,
    TextBlock,
)


def _clause(cid: str, ref: str, kind: ClauseType, *, parent: str | None = None) -> Clause:
    return Clause(
        id=ClauseId(value=cid),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=ref),
        clause_type=kind,
        parent_id=ClauseId(value=parent) if parent else None,
        normative_status=NormativeStatus.NORMATIVE,
        content=(TextBlock(id=f"t-{cid}", text=f"{cid} text"),),
    )


def test_control_mapping_uses_clause_types_without_semantic_classification() -> None:
    document = PublicationDocument(
        key=DocumentKey(value="SAMPLE"),
        title="Sample",
        year=2026,
        clauses=(
            _clause("obj", "4.1", ClauseType.OBJECTIVE),
            _clause("req", "4.1.1", ClauseType.REQUIREMENT, parent="obj"),
        ),
    )
    catalog = GemaraControlMapper(gemara_version="test").map(document)
    assert catalog.controls is not None
    assert len(catalog.controls) == 1
    assert catalog.controls[0].assessment_requirements is not None
    assert [item.id for item in catalog.controls[0].assessment_requirements] == ["ar-req"]
