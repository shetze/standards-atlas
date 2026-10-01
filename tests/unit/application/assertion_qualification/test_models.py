from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)
from standards_atlas.domain.model import ClauseId, EntityAssertionObject

STAT = "http://lunetix.org/standards-atlas#"
CLAUSE = ClauseId(value="c1")


def _span() -> GoldenEvidenceSpan:
    return GoldenEvidenceSpan(
        source_document_key="DOC",
        source_kind="body",
        clause_id=CLAUSE,
        start_offset=0,
        end_offset=4,
        content_hash=hashlib.sha256(b"test").hexdigest(),
    )


def _case() -> AssertionGoldenCase:
    return AssertionGoldenCase(
        source_document_key="DOC",
        clause_id=CLAUSE,
        reference="DOC:1",
        canonical_reference="DOC 1",
        text_sha256=hashlib.sha256(b"test").hexdigest(),
        source_sha256="a" * 64,
        entities=(
            GoldenKnowledgeEntity(id="e1", class_iri=f"{STAT}WorkProduct", normalized_label="Plan"),
            GoldenKnowledgeEntity(
                id="e2", class_iri=f"{STAT}Criterion", normalized_label="Criterion"
            ),
        ),
        assertions=(
            GoldenNormativeAssertion(
                id="a1",
                source_clause_id=CLAUSE,
                subject_id="e1",
                predicate=f"{STAT}specifies",
                object=EntityAssertionObject(entity_id="e2"),
                evidence=(_span(),),
            ),
        ),
    )


def test_golden_suite_keeps_development_and_holdout_as_separate_contracts() -> None:
    suite = AssertionGoldenSuite(
        id="dev",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(review_id="test", review_version="1", audit_sha256="b" * 64),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(_case(),),
    )
    assert suite.partition is AssertionGoldenPartition.DEVELOPMENT


def test_golden_assertion_rejects_unknown_entity_reference() -> None:
    case = _case()
    broken = case.assertions[0].model_copy(update={"subject_id": "missing"})
    with pytest.raises(ValidationError, match="unknown subjects"):
        AssertionGoldenCase(
            source_document_key="DOC",
            clause_id=case.clause_id,
            reference=case.reference,
            canonical_reference=case.canonical_reference,
            text_sha256=case.text_sha256,
            source_sha256=case.source_sha256,
            entities=case.entities,
            assertions=(broken,),
        )


def test_golden_assertion_owner_is_independent_from_multi_source_evidence_owner() -> None:
    assertion = GoldenNormativeAssertion(
        id="a1",
        source_clause_id=CLAUSE,
        subject_id="e1",
        predicate=f"{STAT}specifies",
        object=EntityAssertionObject(entity_id="e2"),
        evidence=(
            GoldenEvidenceSpan(
                source_document_key="DOC",
                source_kind="heading",
                clause_id=ClauseId(value="other"),
                start_offset=0,
                end_offset=4,
                content_hash=hashlib.sha256(b"test").hexdigest(),
            ),
        ),
    )

    assert assertion.source_clause_id == CLAUSE
    assert assertion.evidence[0].clause_id.value == "other"


def test_golden_case_rejects_duplicate_semantic_entities() -> None:
    case = _case()
    duplicate = GoldenKnowledgeEntity(
        id="e3",
        class_iri=case.entities[0].class_iri,
        normalized_label="  PLAN  ",
    )
    with pytest.raises(ValidationError, match="semantically unique"):
        AssertionGoldenCase(
            source_document_key="DOC",
            clause_id=case.clause_id,
            reference=case.reference,
            canonical_reference=case.canonical_reference,
            text_sha256=case.text_sha256,
            source_sha256=case.source_sha256,
            entities=(*case.entities, duplicate),
            assertions=case.assertions,
        )
