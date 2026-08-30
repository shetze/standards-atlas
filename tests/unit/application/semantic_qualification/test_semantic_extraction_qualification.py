from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    SemanticExtractionQualificationConfig,
    qualify_semantic_extractions,
)
from standards_atlas.domain.model import (
    ClauseSemanticExtraction,
    DocumentSemanticExtraction,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionProvenance,
    SemanticResource,
)


def test_semantic_extraction_qualification_scores_ontology_conformance() -> None:
    entity_a = ExtractedEntity(
        id=SemanticResource.stat("entity/a"),
        class_iri=SemanticResource.stat("EngineeringConcept"),
        label="verification",
        confidence=0.9,
        evidence="engineering concept",
    )
    entity_b = ExtractedEntity(
        id=SemanticResource.stat("entity/b"),
        class_iri=SemanticResource.stat("Activity"),
        label="verify",
        confidence=0.8,
        evidence="activity",
    )
    relation = ExtractedRelation(
        subject_id=entity_a.id,
        predicate=SemanticResource.stat("requires"),
        object_id=entity_b.id,
        confidence=0.85,
        evidence="requires verification",
    )
    extraction = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(
            ClauseSemanticExtraction(
                clause_id="c1",
                ontology_versions=("standards-atlas-core@1.1.0",),
                entities=(entity_a, entity_b),
                relations=(relation,),
                provenance=ExtractionProvenance(extractor="test", extractor_version="1.0.0"),
            ),
        ),
    )
    report = qualify_semantic_extractions(
        (extraction,),
        SemanticExtractionQualificationConfig(
            ontology_versions=(
                "standards-atlas-core@1.1.0",
                "functional-safety@1.1.0",
            )
        ),
    )
    assert report.documents == 1
    assert report.clauses == 1
    assert report.ontology_conformance == 1.0
    assert report.gold_available is False
    assert report.entity_f1 is None


def test_semantic_extraction_qualification_fails_when_selected_input_produces_nothing() -> None:
    report = qualify_semantic_extractions(
        (),
        SemanticExtractionQualificationConfig(
            ontology_versions=(
                "standards-atlas-core@1.1.0",
                "functional-safety@1.1.0",
            )
        ),
        expected_clause_count=50,
    )

    assert report.passed is False
    assert report.clauses == 0
    assert report.selected_clause_count == 50
    assert report.eligible_clause_count == 50
    assert report.failures == (
        "no semantic extractions were produced for 50 eligible qualification clauses",
    )


def test_semantic_extraction_qualification_reports_eligibility_counts_and_model() -> None:
    report = qualify_semantic_extractions(
        (),
        SemanticExtractionQualificationConfig(
            ontology_versions=(
                "standards-atlas-core@1.1.0",
                "functional-safety@1.1.0",
            )
        ),
        selected_clause_count=50,
        eligibility_context_clause_count=50,
        eligible_clause_count=32,
        extraction_model="mistral-small-3.2-24b-instruct-q4-k-m",
    )

    assert report.schema_version == "1.4"
    assert report.extraction_model == "mistral-small-3.2-24b-instruct-q4-k-m"
    assert report.selected_clause_count == 50
    assert report.eligibility_context_clause_count == 50
    assert report.eligible_clause_count == 32
    assert report.extracted_clause_count == 0
    assert report.skipped_clause_count == 18
    assert report.passed is False
    assert report.failures == (
        "no semantic extractions were produced for 32 eligible qualification clauses",
    )


def test_semantic_extraction_qualification_fails_on_missing_consensus_context() -> None:
    report = qualify_semantic_extractions(
        (),
        SemanticExtractionQualificationConfig(ontology_versions=("standards-atlas-core@1.1.0",)),
        selected_clause_count=50,
        eligibility_context_clause_count=49,
        eligible_clause_count=0,
    )

    assert report.passed is False
    assert report.failures == (
        "qualification eligibility context accounting mismatch: "
        "49/50 contexts for qualified clauses",
    )


def test_semantic_extraction_qualification_accepts_unqualified_selection_without_context() -> None:
    report = qualify_semantic_extractions(
        (),
        SemanticExtractionQualificationConfig(ontology_versions=("standards-atlas-core@1.1.0",)),
        selected_clause_count=50,
        eligibility_context_clause_count=49,
        expected_eligibility_context_clause_count=49,
        eligible_clause_count=0,
    )

    assert report.passed is True
    assert report.selected_clause_count == 50
    assert report.eligibility_context_clause_count == 49
    assert report.failures == ()


def test_semantic_extraction_qualification_counts_rejected_ontology_terms() -> None:
    from standards_atlas.domain.model import ExtractionViolation

    extraction = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(
            ClauseSemanticExtraction(
                clause_id="c1",
                ontology_versions=("standards-atlas-core@1.1.0",),
                entities=(
                    ExtractedEntity(
                        id=SemanticResource.stat("entity/a"),
                        class_iri=SemanticResource.stat("Activity"),
                        label="activity",
                        confidence=0.9,
                        evidence="valid",
                    ),
                ),
                violations=(
                    ExtractionViolation(
                        kind="undeclared_class",
                        term="http://lunetix.org/standards-atlas#InventedClass",
                        reason="not declared",
                    ),
                    ExtractionViolation(
                        kind="undeclared_property",
                        term="http://lunetix.org/standards-atlas#partOf",
                        reason="not declared",
                    ),
                    ExtractionViolation(
                        kind="invalid_relation",
                        term="http://lunetix.org/standards-atlas#requires",
                        reason="missing entity",
                    ),
                ),
                provenance=ExtractionProvenance(extractor="test", extractor_version="1.0.0"),
            ),
        ),
    )

    report = qualify_semantic_extractions(
        (extraction,),
        SemanticExtractionQualificationConfig(
            ontology_versions=(
                "standards-atlas-core@1.1.0",
                "functional-safety@1.1.0",
            )
        ),
    )

    assert report.schema_version == "1.4"
    assert report.ontology_conformance == 1 / 3
    assert report.ontology_violation_count == 3
    assert report.undeclared_class_count == 1
    assert report.undeclared_property_count == 1
    assert report.invalid_relation_count == 1
    assert report.passed is False
    assert any("ontology conformance" in item for item in report.failures)


def test_semantic_extraction_qualification_reports_non_fatal_llm_failures() -> None:
    from standards_atlas.domain.model import ExtractionFailure

    extraction = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(
            ExtractionFailure(
                clause_id="c1",
                clause_reference="IEC 61508-2:2010 7.4.1",
                clause_title="Verification",
                kind="timeout",
                error_type="LlmTimeoutError",
                message="timed out after 240s",
            ),
            ExtractionFailure(
                clause_id="c2",
                kind="response_error",
                error_type="LlmResponseError",
                message="invalid JSON",
            ),
        ),
    )

    report = qualify_semantic_extractions(
        (extraction,),
        SemanticExtractionQualificationConfig(
            ontology_versions=("standards-atlas-core@1.1.0",),
            timeout_seconds=240,
        ),
        selected_clause_count=2,
        eligibility_context_clause_count=2,
        eligible_clause_count=2,
    )

    assert report.schema_version == "1.4"
    assert report.attempted_clause_count == 2
    assert report.extracted_clause_count == 0
    assert report.extraction_failure_count == 2
    assert report.timeout_count == 1
    assert report.response_error_count == 1
    assert report.extraction_failures[0]["clause_reference"] == "IEC 61508-2:2010 7.4.1"
    assert report.extraction_failures[0]["clause_title"] == "Verification"
    assert report.unavailable_count == 0
    assert report.extraction_timeout_seconds == 240
    assert report.passed is False
    assert any("semantic extraction failed for 2 of 2" in item for item in report.failures)


def _clause_extraction(clause_id: str, *, version: str = "1.0.0") -> ClauseSemanticExtraction:
    return ClauseSemanticExtraction(
        clause_id=clause_id,
        ontology_versions=("standards-atlas-core@1.1.0",),
        provenance=ExtractionProvenance(extractor="test", extractor_version=version),
    )


def _failure(clause_id: str, message: str):
    from standards_atlas.domain.model import ExtractionFailure

    return ExtractionFailure(
        clause_id=clause_id,
        kind="timeout",
        error_type="LlmTimeoutError",
        message=message,
    )


def test_semantic_extraction_merge_promotes_failure_to_success() -> None:
    from standards_atlas.application.semantic_qualification import (
        merge_document_semantic_extractions,
    )

    existing = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(_failure("c1", "old failure"),),
    )
    generated = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(_clause_extraction("c1", version="2.0.0"),),
    )

    merged = merge_document_semantic_extractions(existing, generated)

    assert [item.clause_id for item in merged.clauses] == ["c1"]
    assert merged.failures == ()


def test_semantic_extraction_merge_does_not_degrade_success_to_failure() -> None:
    from standards_atlas.application.semantic_qualification import (
        merge_document_semantic_extractions,
    )

    existing = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(_clause_extraction("c1", version="1.0.0"),),
    )
    generated = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(_failure("c1", "new timeout"),),
    )

    merged = merge_document_semantic_extractions(existing, generated)

    assert merged.clauses[0].provenance.extractor_version == "1.0.0"
    assert merged.failures == ()


def test_semantic_extraction_merge_replaces_failure_with_latest_failure() -> None:
    from standards_atlas.application.semantic_qualification import (
        merge_document_semantic_extractions,
    )

    existing = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(_failure("c1", "old timeout"),),
    )
    generated = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(_failure("c1", "new timeout"),),
    )

    merged = merge_document_semantic_extractions(existing, generated)

    assert merged.clauses == ()
    assert merged.failures[0].message == "new timeout"


def test_semantic_extraction_merge_replaces_success_with_latest_success() -> None:
    from standards_atlas.application.semantic_qualification import (
        merge_document_semantic_extractions,
    )

    existing = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(_clause_extraction("c1", version="1.0.0"),),
    )
    generated = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(_clause_extraction("c1", version="2.0.0"),),
    )

    merged = merge_document_semantic_extractions(existing, generated)

    assert merged.clauses[0].provenance.extractor_version == "2.0.0"
    assert merged.failures == ()


def test_semantic_extraction_merge_preserves_transient_timeout_attempt() -> None:
    from standards_atlas.application.semantic_qualification import (
        merge_document_semantic_extractions,
    )
    from standards_atlas.domain.model import ExtractionAttempt

    existing = DocumentSemanticExtraction(
        source_document_key="doc",
        failures=(_failure("c1", "timeout"),),
        attempts=(
            ExtractionAttempt(
                clause_id="c1",
                status="timeout",
                duration_seconds=240.0,
                error_type="LlmTimeoutError",
                message="timeout",
            ),
        ),
    )
    generated = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(_clause_extraction("c1"),),
        attempts=(ExtractionAttempt(clause_id="c1", status="ok", duration_seconds=12.0),),
    )

    merged = merge_document_semantic_extractions(existing, generated)
    report = qualify_semantic_extractions(
        (merged,),
        SemanticExtractionQualificationConfig(
            ontology_versions=("standards-atlas-core@1.1.0",),
        ),
        selected_clause_count=1,
        eligibility_context_clause_count=1,
        eligible_clause_count=1,
    )

    assert merged.failures == ()
    assert [attempt.status for attempt in merged.attempts] == ["timeout", "ok"]
    assert report.timeout_count == 0
    assert report.timeout_attempt_count == 1
    assert report.extraction_attempt_count == 2
