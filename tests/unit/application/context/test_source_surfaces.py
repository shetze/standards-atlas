import hashlib

import pytest

from standards_atlas.application.context import (
    SourceAccessPolicy,
    SourceMediaKind,
    SourceSurfaceAvailability,
    SourceSurfaceOrigin,
    SourceSurfaceRef,
    SourceSurfaceResolver,
    source_document_binding,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentKnowledge,
    DocumentTable,
    DocumentTableId,
    DocumentType,
    EngineeringDocument,
    EvidenceAnchor,
    EvidenceSourceKind,
    FormulaBlock,
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeEntity,
    SourceEvidence,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def _document(
    *,
    key: str = "TEST",
    version: str | None = "1",
    heading: str | None = "Same source text",
    body: str = "Same source text",
    heading_origin: GeneratedAttribute | None = None,
    extra_content=(),
) -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", year=2026, clause="1"),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        content=(
            TextBlock(
                id="text-1",
                text=body,
                source_evidence=(
                    SourceEvidence(source_id="pdf", source_type="pdf", page_number=1),
                ),
            ),
            *extra_content,
        ),
    ).mark_generated(
        GeneratedAttribute(
            path="baseline.content",
            generator="normalized-content-enrichment",
            method=GenerationMethod.SOURCE_EXTRACTION,
        )
    )
    if heading_origin is not None:
        clause = clause.mark_generated(heading_origin)
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title="Test",
        document_type=DocumentType.STANDARD,
        year=2026,
        version=version,
        clauses=(clause,),
    )


def _heading_source_attribute() -> GeneratedAttribute:
    return GeneratedAttribute(
        path="baseline.heading",
        generator="normalized-content-enrichment",
        method=GenerationMethod.SOURCE_EXTRACTION,
    )


def test_body_and_heading_keep_distinct_surface_identity_even_with_same_text() -> None:
    document = _document(heading_origin=_heading_source_attribute())
    resolver = SourceSurfaceResolver((document,))

    body = resolver.resolve(
        SourceSurfaceRef(
            document_key="TEST",
            clause_id="c1",
            source_kind=EvidenceSourceKind.BODY,
        )
    )
    heading = resolver.resolve(
        SourceSurfaceRef(
            document_key="TEST",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )

    assert body.availability is SourceSurfaceAvailability.AVAILABLE
    assert heading.availability is SourceSurfaceAvailability.AVAILABLE
    assert body.text == heading.text == "Same source text"
    assert body.content_sha256 == heading.content_sha256
    assert body.identity is not None and heading.identity is not None
    assert body.identity.source_kind is EvidenceSourceKind.BODY
    assert heading.identity.source_kind is EvidenceSourceKind.HEADING
    assert body.origin is SourceSurfaceOrigin.SOURCE_EXTRACTION
    assert heading.origin is SourceSurfaceOrigin.SOURCE_EXTRACTION
    assert body.source_backed is True
    assert heading.source_backed is True


def test_heading_origin_does_not_promote_synthetic_or_unattributed_text() -> None:
    synthetic = _document(
        key="SYNTHETIC",
        heading="Part 7",
        heading_origin=GeneratedAttribute(
            path="baseline.heading",
            generator="document-selection-synthetic-display-label",
            method=GenerationMethod.DETERMINISTIC,
        ),
    )
    unresolved = _document(key="UNRESOLVED", heading="Imported display heading")
    resolver = SourceSurfaceResolver((synthetic, unresolved))

    synthetic_result = resolver.resolve(
        SourceSurfaceRef(
            document_key="SYNTHETIC",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )
    unresolved_result = resolver.resolve(
        SourceSurfaceRef(
            document_key="UNRESOLVED",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )

    assert synthetic_result.origin is SourceSurfaceOrigin.SYNTHETIC_DISPLAY_LABEL
    assert synthetic_result.source_backed is False
    assert unresolved_result.origin is SourceSurfaceOrigin.UNRESOLVED
    assert unresolved_result.source_backed is False


def test_confirmed_heading_assignment_is_distinct_from_source_extraction() -> None:
    document = _document(key="CONFIRMED")
    clause = document.clauses[0].confirm_authoritative(
        "baseline.heading", authority="reviewed-heading-assignment"
    )
    document = document.model_copy(update={"clauses": (clause,)})

    result = SourceSurfaceResolver((document,)).resolve(
        SourceSurfaceRef(
            document_key="CONFIRMED",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )

    assert result.origin is SourceSurfaceOrigin.CONFIRMED_SOURCE_ASSIGNMENT
    assert result.origin_reference == "reviewed-heading-assignment"
    assert result.source_backed is True


def test_missing_heading_and_unauthorized_text_are_explicit_and_do_not_leak() -> None:
    missing = _document(key="MISSING", heading=None)
    protected = _document(key="PROTECTED", heading_origin=_heading_source_attribute())
    resolver = SourceSurfaceResolver(
        (missing, protected),
        access_policy=SourceAccessPolicy(allowed_document_keys=("PROTECTED",), expose_text=False),
    )

    denied_document = resolver.resolve(
        SourceSurfaceRef(
            document_key="MISSING",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )
    denied_text = resolver.resolve(
        SourceSurfaceRef(
            document_key="PROTECTED",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )

    assert denied_document.availability is SourceSurfaceAvailability.NOT_AUTHORIZED
    assert denied_text.availability is SourceSurfaceAvailability.NOT_AUTHORIZED
    for result in (denied_document, denied_text):
        assert result.text is None
        assert result.surface_sha256 is None
        assert result.content_sha256 is None
        assert result.start_offset is None
        assert result.end_offset is None

    missing_result = SourceSurfaceResolver((missing,)).resolve(
        SourceSurfaceRef(
            document_key="MISSING",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        )
    )
    assert missing_result.availability is SourceSurfaceAvailability.MISSING


def test_document_revision_prevents_implicit_selection_of_another_edition() -> None:
    first = _document(key="SAME", version="1", heading_origin=_heading_source_attribute())
    second = _document(key="SAME", version="2", heading_origin=_heading_source_attribute())
    first_binding = source_document_binding(first)
    second_binding = source_document_binding(second)
    resolver = SourceSurfaceResolver((first, second))

    ambiguous = resolver.resolve(
        SourceSurfaceRef(
            document_key="SAME",
            clause_id="c1",
            source_kind=EvidenceSourceKind.BODY,
        )
    )
    selected = resolver.resolve(
        SourceSurfaceRef(
            document_key="SAME",
            document_revision=second_binding.source_revision,
            clause_id="c1",
            source_kind=EvidenceSourceKind.BODY,
        )
    )
    wrong = resolver.resolve(
        SourceSurfaceRef(
            document_key="SAME",
            document_revision="sha256:" + ("0" * 64),
            clause_id="c1",
            source_kind=EvidenceSourceKind.BODY,
        )
    )

    assert first_binding.source_revision != second_binding.source_revision
    assert ambiguous.availability is SourceSurfaceAvailability.CONFLICTING
    assert selected.availability is SourceSurfaceAvailability.AVAILABLE
    assert selected.identity is not None
    assert selected.identity.document.version == "2"
    assert wrong.availability is SourceSurfaceAvailability.CONFLICTING


def test_exact_excerpt_offsets_use_unmodified_canonical_surface() -> None:
    document = _document(
        heading="  Heading with space  ",
        heading_origin=_heading_source_attribute(),
    )
    resolver = SourceSurfaceResolver((document,))

    result = resolver.resolve(
        SourceSurfaceRef(
            document_key="TEST",
            clause_id="c1",
            source_kind=EvidenceSourceKind.HEADING,
        ),
        start_offset=2,
        end_offset=9,
    )

    assert result.text == "Heading"
    assert result.start_offset == 2
    assert result.end_offset == 9
    assert (
        result.surface_sha256 == "sha256:" + hashlib.sha256(b"  Heading with space  ").hexdigest()
    )
    with pytest.raises(ValueError, match="exceed"):
        resolver.resolve(
            result.requested,
            start_offset=2,
            end_offset=99,
        )


def test_table_and_formula_handles_keep_real_textual_availability() -> None:
    evidence = (SourceEvidence(source_id="pdf", source_type="pdf", page_number=3),)
    table = TableBlock(
        id="table-block",
        rows=(TableRow(cells=(TableCell(text="A"),)),),
        source_evidence=evidence,
    )
    visual_formula = FormulaBlock(
        id="formula-visual",
        expression="",
        extraction_status="visual_only",
        source_evidence=evidence,
        content_hash="f" * 64,
    )
    textual_formula = FormulaBlock(
        id="formula-text",
        expression=r"a^2+b^2=c^2",
        representation="latex",
        extraction_status="human_verified",
        source_evidence=evidence,
    )
    document = _document(
        heading_origin=_heading_source_attribute(),
        extra_content=(table, visual_formula, textual_formula),
    )
    document = document.model_copy(
        update={
            "tables": (
                DocumentTable(
                    id=DocumentTableId(value="table-1"),
                    reference="Table 1",
                    parent_clause_id=document.clauses[0].id,
                    sequence_index=0,
                    table_block_id="table-block",
                ),
            )
        }
    )
    resolver = SourceSurfaceResolver((document,))
    refs = resolver.list_surface_refs(document_key="TEST", clause_id="c1")

    assert {(item.media_kind, item.block_id) for item in refs if item.media_kind is not None} >= {
        (SourceMediaKind.TABLE, "table-block"),
        (SourceMediaKind.FORMULA, "formula-visual"),
        (SourceMediaKind.FORMULA, "formula-text"),
    }

    table_result = resolver.resolve(
        SourceSurfaceRef(
            document_key="TEST",
            clause_id="c1",
            media_kind=SourceMediaKind.TABLE,
            block_id="table-block",
        )
    )
    visual_result = resolver.resolve(
        SourceSurfaceRef(
            document_key="TEST",
            clause_id="c1",
            media_kind=SourceMediaKind.FORMULA,
            block_id="formula-visual",
        )
    )
    textual_ref = SourceSurfaceRef(
        document_key="TEST",
        clause_id="c1",
        media_kind=SourceMediaKind.FORMULA,
        block_id="formula-text",
    )
    textual_result = resolver.resolve(textual_ref)
    protected_formula = SourceSurfaceResolver(
        (document,), access_policy=SourceAccessPolicy(expose_text=False)
    ).resolve(textual_ref)

    assert table_result.availability is SourceSurfaceAvailability.NON_TEXTUAL
    assert table_result.media is not None
    assert table_result.media.document_table_id == "table-1"
    assert table_result.text is None
    assert visual_result.availability is SourceSurfaceAvailability.NON_TEXTUAL
    assert visual_result.media is not None
    assert visual_result.media.formula_extraction_status == "visual_only"
    assert textual_result.availability is SourceSurfaceAvailability.AVAILABLE
    assert textual_result.text == r"a^2+b^2=c^2"
    assert textual_result.origin is SourceSurfaceOrigin.SOURCE_EXTRACTION
    assert protected_formula.availability is SourceSurfaceAvailability.NOT_AUTHORIZED
    assert protected_formula.text is None
    assert protected_formula.surface_sha256 is None
    assert protected_formula.content_sha256 is None
    assert protected_formula.media is not None
    assert protected_formula.media.media_content_hash is None


def test_source_revision_excludes_accepted_document_knowledge() -> None:
    document = _document(heading_origin=_heading_source_attribute())
    text = document.clauses[0].plain_text
    digest = hashlib.sha256(text.encode()).hexdigest()
    anchor = EvidenceAnchor(
        id="a1",
        source_clause_id=document.clauses[0].id,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(text),
        content_hash=digest,
    )
    knowledge = DocumentKnowledge(
        ontology_versions=("standards-atlas-core@2.0.0",),
        evidence_anchors=(anchor,),
        entities=(
            KnowledgeEntity(
                id="e1",
                class_iri="https://standards-atlas.example/EngineeringEntity",
                normalized_label="example",
                source_anchor_ids=("a1",),
            ),
        ),
    )
    with_knowledge = document.model_copy(update={"knowledge": knowledge})

    assert (
        source_document_binding(document).source_revision
        == source_document_binding(with_knowledge).source_revision
    )
