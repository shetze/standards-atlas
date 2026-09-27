"""Two explicit offline entrances into one clause-local assertion evaluator."""

from __future__ import annotations

from collections.abc import Sequence

from standards_atlas.application.assertion_qualification.audit import (
    AssertionReviewAudit,
    canonical_sha256,
)
from standards_atlas.application.assertion_qualification.matching import (
    aggregate_case_reports,
    evaluate_case,
)
from standards_atlas.application.assertion_qualification.models import (
    ASSERTION_EVALUATION_CONTRACT,
    AssertionGoldenSuite,
    AssertionQualificationProposalSource,
    AssertionQualificationReport,
    OntologyResourceBinding,
)
from standards_atlas.application.assertion_qualification.projection import (
    ClauseEvaluationCandidate,
    project_native_proposal,
    project_review_snapshot,
)
from standards_atlas.application.assertion_qualification.source_resolution import (
    FrozenSourceResolver,
)
from standards_atlas.application.formal_semantics import (
    ResourceFormalOntologyRepository,
    load_formal_class_hierarchy,
)
from standards_atlas.domain.model import DocumentKnowledgeProposal


class AssertionQualificationEvaluator:
    """Measure stored candidates without running models or applying an adoption policy."""

    def evaluate(
        self,
        suite: AssertionGoldenSuite,
        proposals: Sequence[DocumentKnowledgeProposal] | None = None,
        *,
        review_audit: AssertionReviewAudit | None = None,
        source_audit: AssertionReviewAudit | None = None,
    ) -> AssertionQualificationReport:
        if (proposals is None) == (review_audit is None):
            raise ValueError("exactly one candidate source is required: proposals or review_audit")
        if review_audit is not None and source_audit is not None:
            raise ValueError("source_audit is only valid for native proposal candidates")
        audit = review_audit if review_audit is not None else source_audit
        if audit is not None:
            validate_audit_binding(suite, audit)

        if review_audit is not None:
            candidates = {
                case.case_key: project_review_snapshot(
                    review_audit,
                    document_key=case.source_document_key,
                    clause_id=case.clause_id.value,
                )
                for case in suite.cases
            }
            sources = ()
            candidate_mode = "review_snapshot"
        else:
            assert proposals is not None
            candidates, sources = _native_inputs(suite, proposals)
            candidate_mode = "native_proposal"

        # Both inputs use one comparison path. Source integrity is evaluated only
        # against the exact byte-bound audit when that source basis is actually supplied.
        source_resolver = FrozenSourceResolver.from_audit(audit) if audit is not None else None
        ontology_repository = ResourceFormalOntologyRepository()
        class_hierarchy = load_formal_class_hierarchy(
            suite.ontology_versions, repository=ontology_repository
        )
        ontology_resources = _ontology_resource_bindings(
            suite.ontology_versions, ontology_repository
        )
        case_reports = tuple(
            evaluate_case(
                case,
                candidates.get(case.case_key),
                class_hierarchy=class_hierarchy,
                source_resolver=source_resolver,
            ).report
            for case in suite.cases
        )
        return AssertionQualificationReport(
            evaluation_contract=ASSERTION_EVALUATION_CONTRACT,
            candidate_mode=candidate_mode,
            audit=suite.audit,
            source_binding="audit_verified" if audit is not None else "golden_declared",
            golden_suite_id=suite.id,
            golden_suite_version=suite.version,
            golden_partition=suite.partition,
            golden_suite_hash=golden_suite_sha256(suite),
            ontology_versions=suite.ontology_versions,
            ontology_resources=ontology_resources,
            proposal_sources=sources,
            cases=case_reports,
            aggregate=aggregate_case_reports(case_reports),
        )


def _ontology_resource_bindings(
    ontology_versions: tuple[str, ...],
    repository: ResourceFormalOntologyRepository,
) -> tuple[OntologyResourceBinding, ...]:
    bindings: list[OntologyResourceBinding] = []
    for reference in ontology_versions:
        ontology_id, version = reference.rsplit("@", 1)
        definition = repository.load(ontology_id, version)
        bindings.append(
            OntologyResourceBinding(
                reference=reference,
                ontology_iri=definition.ontology_iri,
                version_iri=definition.version_iri,
                resource=definition.resource,
                resource_sha256=repository.resource_sha256(ontology_id, version),
            )
        )
    return tuple(bindings)


def _native_inputs(
    suite: AssertionGoldenSuite,
    proposals: Sequence[DocumentKnowledgeProposal],
) -> tuple[
    dict[tuple[str, str], ClauseEvaluationCandidate],
    tuple[AssertionQualificationProposalSource, ...],
]:
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
    hashes = {key: proposal_sha256(proposal) for key, proposal in by_document.items()}
    candidates = {
        case.case_key: project_native_proposal(
            by_document[case.source_document_key],
            case.clause_id.value,
            proposal_hash=hashes[case.source_document_key],
        )
        for case in suite.cases
        if case.source_document_key in by_document
    }
    sources = tuple(
        AssertionQualificationProposalSource(
            source_document_key=key,
            proposal_run_id=proposal.proposal_run_id,
            proposal_hash=hashes[key],
            extractor=proposal.proposal_provenance.extractor,
            extractor_version=proposal.proposal_provenance.extractor_version,
            model=proposal.proposal_provenance.model,
            provider=proposal.proposal_provenance.provider,
            prompt_version=proposal.proposal_provenance.prompt_version,
        )
        for key, proposal in sorted(by_document.items())
    )
    return candidates, sources


def golden_suite_sha256(suite: AssertionGoldenSuite) -> str:
    return canonical_sha256(suite.model_dump(mode="json"))


def proposal_sha256(proposal: DocumentKnowledgeProposal) -> str:
    return canonical_sha256(proposal.model_dump(mode="json"))


def validate_audit_binding(suite: AssertionGoldenSuite, audit: AssertionReviewAudit) -> None:
    """Require exact bytes, selection, sources and confirmed golden expectations."""
    from standards_atlas.application.assertion_qualification.review_pilot import (
        publish_assertion_review_pilot,
    )

    if suite.audit.audit_sha256 != audit.audit_sha256:
        raise ValueError("review audit SHA-256 does not match golden suite binding")
    expected = publish_assertion_review_pilot(audit)
    if golden_suite_sha256(expected) != golden_suite_sha256(suite):
        raise ValueError("golden suite content/selection does not match the bound review audit")
