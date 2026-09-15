"""Reproducible Slice-7A evaluation of knowledge proposals against a golden suite."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from standards_atlas.application.assertion_qualification.matching import (
    aggregate_case_reports,
    evaluate_case,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionGoldenSuite,
    AssertionQualificationProposalSource,
    AssertionQualificationReport,
)
from standards_atlas.domain.model import DocumentKnowledgeProposal


class AssertionQualificationEvaluator:
    """Measure proposal quality without applying acceptance thresholds or adoption policy."""

    def evaluate(
        self,
        suite: AssertionGoldenSuite,
        proposals: Sequence[DocumentKnowledgeProposal],
    ) -> AssertionQualificationReport:
        by_document: dict[str, DocumentKnowledgeProposal] = {}
        for proposal in proposals:
            if proposal.source_document_key in by_document:
                raise ValueError(
                    "assertion qualification accepts at most one proposal per source document: "
                    f"{proposal.source_document_key!r}"
                )
            if set(proposal.ontology_versions) != set(suite.ontology_versions):
                raise ValueError(
                    "proposal ontology versions do not match assertion golden suite for "
                    f"{proposal.source_document_key!r}"
                )
            by_document[proposal.source_document_key] = proposal

        expected_documents = {case.source_document_key for case in suite.cases}
        unexpected = set(by_document) - expected_documents
        if unexpected:
            raise ValueError(
                "assertion qualification proposals are outside the golden suite: "
                f"{sorted(unexpected)!r}"
            )

        proposal_hashes = {key: proposal_sha256(proposal) for key, proposal in by_document.items()}
        case_reports = tuple(
            evaluate_case(
                case,
                by_document.get(case.source_document_key),
                proposal_hash=proposal_hashes.get(case.source_document_key),
            ).report
            for case in suite.cases
        )
        sources = tuple(
            AssertionQualificationProposalSource(
                source_document_key=key,
                proposal_run_id=proposal.proposal_run_id,
                proposal_hash=proposal_hashes[key],
                extractor=proposal.proposal_provenance.extractor,
                extractor_version=proposal.proposal_provenance.extractor_version,
                model=proposal.proposal_provenance.model,
                provider=proposal.proposal_provenance.provider,
                prompt_version=proposal.proposal_provenance.prompt_version,
            )
            for key, proposal in sorted(by_document.items())
        )
        return AssertionQualificationReport(
            golden_suite_id=suite.id,
            golden_suite_version=suite.version,
            golden_partition=suite.partition,
            golden_suite_hash=golden_suite_sha256(suite),
            ontology_versions=suite.ontology_versions,
            proposal_sources=sources,
            cases=case_reports,
            aggregate=aggregate_case_reports(case_reports),
        )


def golden_suite_sha256(suite: AssertionGoldenSuite) -> str:
    return _model_sha256(suite.model_dump(mode="json"))


def proposal_sha256(proposal: DocumentKnowledgeProposal) -> str:
    return _model_sha256(proposal.model_dump(mode="json"))


def _model_sha256(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
