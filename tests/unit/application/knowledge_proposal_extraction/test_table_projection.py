import hashlib

import pytest

from standards_atlas.application.knowledge_proposal_extraction import (
    TABLE_KNOWLEDGE_PROJECTION_VERSION,
    DocumentKnowledgeProposalUnifier,
    TableKnowledgeProposalProjector,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    NoteBlock,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


def _matrix_document(
    headers: tuple[str, str],
    rows: tuple[tuple[str, str], ...],
    *,
    nested: bool = False,
) -> EngineeringDocument:
    table = TableBlock(
        id="matrix",
        caption="Structured knowledge matrix",
        rows=(
            TableRow(cells=tuple(TableCell(text=value, is_header=True) for value in headers)),
            *(TableRow(cells=tuple(TableCell(text=value) for value in values)) for values in rows),
        ),
    )
    table_content = NoteBlock(id="note", note_kind="NOTE", content=(table,)) if nested else table
    clause = Clause(
        id=ClauseId(value="matrix-clause"),
        reference=StandardReference(standard="DOMAIN", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="intro", text="Introductory text."), table_content),
    )
    return EngineeringDocument(
        key=DocumentKey(value="DOMAIN"),
        title="Domain document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def _project(document: EngineeringDocument):
    return TableKnowledgeProposalProjector().project_document(
        document,
        proposal_run_id="table-run",
        ontology_versions=ONTOLOGIES,
    )


def _recommendation_document() -> EngineeringDocument:
    table = TableBlock(
        id="table-a2",
        caption="Table A.2 — Software architecture design (see 7.4.3)",
        rows=(
            TableRow(
                cells=tuple(
                    TableCell(text=value, is_header=True)
                    for value in (
                        "Ref",
                        "Technique/measure",
                        "See IEC 61508-7",
                        "SIL 1",
                        "SIL 2",
                        "SIL 3",
                        "SIL 4",
                    )
                )
            ),
            TableRow(
                cells=tuple(
                    TableCell(text=value)
                    for value in (
                        "1b",
                        "Formal methods",
                        "B.2.2, C.2.4",
                        "—",
                        "R",
                        "R",
                        "HR",
                    )
                )
            ),
        ),
    )
    clause = Clause(
        id=ClauseId(value="iec61508-3-a2"),
        reference=StandardReference(standard="IEC61508-3", clause="A.2"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    return EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="IEC 61508-3",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def _labels(proposal):
    return {entity.normalized_label: entity for entity in proposal.entity_proposals}


def _evidence_text(document: EngineeringDocument, proposal, anchor_id: str) -> str:
    anchor = next(item for item in proposal.evidence_anchors if item.id == anchor_id)
    clause = document.clauses[0]
    assert anchor.start_offset is not None
    assert anchor.end_offset is not None
    text = clause.plain_text[anchor.start_offset : anchor.end_offset]
    assert anchor.content_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text


def test_projects_work_product_matrix_as_work_product_produced_by_activity() -> None:
    document = _matrix_document(
        ("Activity", "Work product"),
        (("Review", "Review report"),),
        nested=True,
    )

    proposal = _project(document)

    assert proposal.proposal_provenance.extractor == "structured-table-projector"
    assert proposal.proposal_provenance.extractor_version == TABLE_KNOWLEDGE_PROJECTION_VERSION
    assert proposal.attempts == ()
    assert proposal.failures == ()
    assert proposal.violations == ()
    labels = _labels(proposal)
    assert labels["review"].class_iri == f"{STAT}Activity"
    assert labels["review report"].class_iri == f"{STAT}WorkProduct"
    assertion = proposal.assertion_proposals[0]
    assert assertion.subject_id == labels["review report"].id
    assert assertion.predicate == f"{STAT}producedBy"
    assert assertion.object.kind == "entity"
    assert assertion.object.entity_id == labels["review"].id
    assert assertion.normative_force.value == "unspecified"
    assert {
        _evidence_text(document, proposal, anchor_id) for anchor_id in assertion.evidence_anchor_ids
    } == {"Review", "Review report"}


def test_projects_responsibility_traceability_and_verification_criteria_matrices() -> None:
    cases = (
        (
            ("Responsible role", "Task"),
            ("Safety manager", "Approve plan"),
            (f"{STAT}Role", f"{STAT}EngineeringEntity", f"{STAT}responsibleFor"),
        ),
        (
            ("Source requirement", "Target test"),
            ("REQ-1", "TEST-7"),
            (
                f"{STAT}EngineeringEntity",
                f"{STAT}EngineeringEntity",
                f"{STAT}tracesTo",
            ),
        ),
        (
            ("Subject", "Verification criterion"),
            ("Verification plan", "Independent review"),
            (f"{STAT}EngineeringEntity", f"{STAT}Criterion", f"{STAT}requires"),
        ),
    )

    for headers, values, expected in cases:
        proposal = _project(_matrix_document(headers, (values,)))
        assert len(proposal.entity_proposals) == 2
        assert len(proposal.assertion_proposals) == 1
        assert proposal.entity_proposals[0].class_iri == expected[0]
        assert proposal.entity_proposals[1].class_iri == expected[1]
        assert proposal.assertion_proposals[0].predicate == expected[2]


def test_repeated_cell_text_is_grounded_by_structure_not_ambiguous_text_search() -> None:
    document = _matrix_document(
        ("Source requirement", "Target test"),
        (("Repeated", "TEST-1"), ("Repeated", "TEST-2")),
    )

    proposal = _project(document)

    repeated = [
        entity for entity in proposal.entity_proposals if entity.normalized_label == "repeated"
    ]
    assert len(repeated) == 2
    first_anchor = next(
        item for item in proposal.evidence_anchors if item.id == repeated[0].source_anchor_ids[0]
    )
    second_anchor = next(
        item for item in proposal.evidence_anchors if item.id == repeated[1].source_anchor_ids[0]
    )
    assert first_anchor.start_offset != second_anchor.start_offset
    assert _evidence_text(document, proposal, first_anchor.id) == "Repeated"
    assert _evidence_text(document, proposal, second_anchor.id) == "Repeated"


def test_row_spanning_source_cell_reuses_one_structural_entity_anchor() -> None:
    table = TableBlock(
        id="matrix",
        caption="Responsibilities",
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Responsible role", is_header=True),
                    TableCell(text="Task", is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="Safety manager", row_span=2),
                    TableCell(text="Approve plan"),
                )
            ),
            TableRow(cells=(TableCell(text="Approve report"),)),
        ),
    )
    clause = Clause(
        id=ClauseId(value="matrix-clause"),
        reference=StandardReference(standard="DOMAIN", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOMAIN"),
        title="Domain document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )

    proposal = _project(document)

    managers = [
        entity
        for entity in proposal.entity_proposals
        if entity.normalized_label == "safety manager"
    ]
    assert len(managers) == 1
    assert len(proposal.assertion_proposals) == 2
    assert all(assertion.subject_id == managers[0].id for assertion in proposal.assertion_proposals)


def test_unsupported_table_kinds_do_not_create_assertion_proposals() -> None:
    generic = _matrix_document(("Name", "Comment"), (("Alpha", "Example"),))
    applicability = _matrix_document(
        ("Subject", "Applicability"),
        (("Method A", "SIL 2"),),
    )

    assert _project(generic).entity_proposals == ()
    assert _project(generic).assertion_proposals == ()
    assert _project(applicability).entity_proposals == ()
    assert _project(applicability).assertion_proposals == ()


def test_rejects_ontology_selection_without_required_core_vocabulary() -> None:
    document = _matrix_document(("Activity", "Work product"), (("Review", "Report"),))

    with pytest.raises(ValueError, match="not declared"):
        TableKnowledgeProposalProjector().project_document(
            document,
            proposal_run_id="table-run",
            ontology_versions=("functional-safety@2.1.0",),
        )


def test_projects_qualified_technique_recommendations_without_flattening() -> None:
    document = _recommendation_document()

    proposal = _project(document)

    by_class: dict[str, list] = {}
    for entity in proposal.entity_proposals:
        by_class.setdefault(entity.class_iri, []).append(entity)
    assert len(by_class[f"{STAT}TechniqueRecommendation"]) == 4
    assert len(by_class[f"{STAT}SafetyTechniqueOrMeasure"]) == 1
    assert len(by_class[f"{STAT}SafetyIntegrityLevel"]) == 4
    assert len(by_class[f"{STAT}RecommendationLevel"]) == 4

    predicates = [item.predicate for item in proposal.assertion_proposals]
    assert predicates.count(f"{STAT}recommendsTechnique") == 4
    assert predicates.count(f"{STAT}hasIntegrityLevel") == 4
    assert predicates.count(f"{STAT}hasRecommendationLevel") == 4
    assert predicates.count(f"{STAT}localIdentifier") == 4
    assert predicates.count(f"{STAT}alternativeGroup") == 4
    assert predicates.count(f"{STAT}descriptionReference") == 8
    assert predicates.count(f"{STAT}contextReference") == 4
    assert all(item.normative_force.value == "unspecified" for item in proposal.assertion_proposals)

    literals = {
        (item.predicate, item.object.value)
        for item in proposal.assertion_proposals
        if item.object.kind == "literal"
    }
    assert (f"{STAT}localIdentifier", "1b") in literals
    assert (f"{STAT}alternativeGroup", "1") in literals
    assert (f"{STAT}descriptionReference", "IEC61508-7:B.2.2") in literals
    assert (f"{STAT}descriptionReference", "IEC61508-7:C.2.4") in literals
    assert (f"{STAT}contextReference", "IEC61508-3:7.4.3") in literals

    evidence = {
        _evidence_text(document, proposal, anchor.id) for anchor in proposal.evidence_anchors
    }
    assert {
        "Formal methods",
        "1b",
        "SIL 1",
        "SIL 2",
        "SIL 3",
        "SIL 4",
        "—",
        "R",
        "HR",
        "B.2.2",
        "C.2.4",
        "7.4.3",
    } <= evidence


def test_unification_preserves_reified_recommendations_and_merges_shared_levels() -> None:
    proposal = _project(_recommendation_document())

    unified = DocumentKnowledgeProposalUnifier().unify(
        (proposal,), proposal_run_id="unified-table-run"
    )

    by_class: dict[str, list] = {}
    for entity in unified.entity_proposals:
        by_class.setdefault(entity.class_iri, []).append(entity)
    assert len(by_class[f"{STAT}TechniqueRecommendation"]) == 4
    assert len(by_class[f"{STAT}SafetyTechniqueOrMeasure"]) == 1
    assert len(by_class[f"{STAT}SafetyIntegrityLevel"]) == 4
    levels = by_class[f"{STAT}RecommendationLevel"]
    assert {item.normalized_label for item in levels} == {
        "neutral",
        "recommended",
        "highly recommended",
    }
    recommended = next(item for item in levels if item.normalized_label == "recommended")
    assert len(recommended.source_anchor_ids) == 2
    assert len(unified.assertion_proposals) == len(proposal.assertion_proposals)


def test_qualified_recommendations_require_functional_safety_2_1_vocabulary() -> None:
    with pytest.raises(ValueError, match="Formal Ontology 2.1 vocabulary"):
        TableKnowledgeProposalProjector().project_document(
            _recommendation_document(),
            proposal_run_id="legacy-ontology-run",
            ontology_versions=("standards-atlas-core@2.0.0",),
        )
