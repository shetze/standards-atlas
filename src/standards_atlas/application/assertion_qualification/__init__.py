"""Assertion-centred qualification contracts and deterministic Slice-7A metrics."""

from .evaluation import (
    AssertionQualificationEvaluator,
    golden_suite_sha256,
    proposal_sha256,
)
from .io import (
    load_assertion_golden_suite,
    load_document_knowledge_proposal,
    write_assertion_qualification_report,
)
from .models import (
    ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION,
    ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION,
    AccuracyMetrics,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationAggregate,
    AssertionQualificationCaseReport,
    AssertionQualificationProposalSource,
    AssertionQualificationReport,
    CountMetrics,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)

__all__ = [
    "ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION",
    "ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION",
    "AccuracyMetrics",
    "AssertionGoldenCase",
    "AssertionGoldenPartition",
    "AssertionGoldenSuite",
    "AssertionQualificationAggregate",
    "AssertionQualificationCaseReport",
    "AssertionQualificationEvaluator",
    "AssertionQualificationProposalSource",
    "AssertionQualificationReport",
    "CountMetrics",
    "GoldenEvidenceSpan",
    "GoldenKnowledgeEntity",
    "GoldenNormativeAssertion",
    "golden_suite_sha256",
    "load_assertion_golden_suite",
    "load_document_knowledge_proposal",
    "proposal_sha256",
    "write_assertion_qualification_report",
]
