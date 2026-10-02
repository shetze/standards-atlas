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
    AssertionGoldenCase,
    AssertionGoldenSuite,
    AssertionQualificationProposalSource,
    AssertionQualificationReport,
    CandidateSourceComparison,
    CandidateSourceComparisonStatus,
    OntologyResourceBinding,
)
from standards_atlas.application.assertion_qualification.projection import (
    ClauseEvaluationCandidate,
    project_native_proposal,
    project_review_snapshot,
)
from standards_atlas.application.assertion_qualification.source_resolution import (
    FrozenSourceKey,
    FrozenSourceResolver,
    NativeSourcePackageResolver,
)
from standards_atlas.application.context import ContextSourcePackage, context_source_package_binding
from standards_atlas.application.formal_semantics import (
    ResourceFormalOntologyRepository,
    load_formal_class_hierarchy,
)
from standards_atlas.domain.model import DocumentKnowledgeProposal, EvidenceSourceKind


class AssertionQualificationEvaluator:
    """Measure stored candidates without running models or applying an adoption policy."""

    def evaluate(
        self,
        suite: AssertionGoldenSuite,
        proposals: Sequence[DocumentKnowledgeProposal] | None = None,
        *,
        review_audit: AssertionReviewAudit | None = None,
        source_audit: AssertionReviewAudit | None = None,
        source_packages: Sequence[ContextSourcePackage] | None = None,
    ) -> AssertionQualificationReport:
        if (proposals is None) == (review_audit is None):
            raise ValueError("exactly one candidate source is required: proposals or review_audit")
        if review_audit is not None and source_audit is not None:
            raise ValueError("source_audit is only valid for native proposal candidates")
        if review_audit is not None and source_packages is not None:
            raise ValueError("source_packages are only valid for native proposal candidates")
        audit = review_audit if review_audit is not None else source_audit
        if audit is not None:
            validate_audit_binding(suite, audit)

        historical_resolver = FrozenSourceResolver.from_audit(audit) if audit is not None else None
        package_by_hash: dict[str, ContextSourcePackage] = {}
        proposal_by_document: dict[str, DocumentKnowledgeProposal] = {}

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
            source_binding = "audit_verified"
        else:
            assert proposals is not None
            candidates, sources = _native_inputs(suite, proposals)
            proposal_by_document = {item.source_document_key: item for item in proposals}
            candidate_mode = "native_proposal"
            if source_packages is not None:
                package_by_hash, complete = _native_source_packages(proposals, source_packages)
                source_binding = (
                    "native_package_verified" if complete else "native_package_partial"
                )
            elif source_audit is not None:
                # Historical AP01 replay remains available as a frozen-source entrance. Current
                # source-package evaluation never falls back to these historical source bytes.
                source_binding = "audit_verified"
            else:
                source_binding = "golden_declared"

        ontology_repository = ResourceFormalOntologyRepository()
        class_hierarchy = load_formal_class_hierarchy(
            suite.ontology_versions, repository=ontology_repository
        )
        ontology_resources = _ontology_resource_bindings(
            suite.ontology_versions, ontology_repository
        )

        case_reports = []
        for case in suite.cases:
            resolver = historical_resolver
            comparison = CandidateSourceComparison()
            if review_audit is None and source_packages is not None:
                proposal = proposal_by_document.get(case.source_document_key)
                resolver, comparison = _native_case_source(
                    case,
                    proposal,
                    package_by_hash,
                    historical_resolver=historical_resolver,
                )
            result = evaluate_case(
                case,
                candidates.get(case.case_key),
                class_hierarchy=class_hierarchy,
                source_resolver=resolver,
            ).report
            if review_audit is None and source_packages is not None:
                result = result.model_copy(update={"source_comparison": comparison})
            case_reports.append(result)

        reports = tuple(case_reports)
        return AssertionQualificationReport(
            evaluation_contract=ASSERTION_EVALUATION_CONTRACT,
            candidate_mode=candidate_mode,
            audit=suite.audit,
            source_binding=source_binding,
            golden_suite_id=suite.id,
            golden_suite_version=suite.version,
            golden_partition=suite.partition,
            golden_suite_hash=golden_suite_sha256(suite),
            ontology_versions=suite.ontology_versions,
            ontology_resources=ontology_resources,
            proposal_sources=sources,
            cases=reports,
            aggregate=aggregate_case_reports(reports),
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
            request_contract_id=proposal.proposal_provenance.request_contract_id,
            output_contract_id=proposal.proposal_provenance.output_contract_id,
            source_binding_contract_id=proposal.proposal_provenance.source_binding_contract_id,
            context_source_bindings=proposal.context_source_bindings,
        )
        for key, proposal in sorted(by_document.items())
    )
    return candidates, sources


def _native_source_packages(
    proposals: Sequence[DocumentKnowledgeProposal],
    packages: Sequence[ContextSourcePackage],
) -> tuple[dict[str, ContextSourcePackage], bool]:
    declared = {
        binding.package_sha256: binding
        for proposal in proposals
        for binding in proposal.context_source_bindings
    }
    if not declared:
        raise ValueError("native source-package evaluation requires proposal source bindings")
    package_by_hash: dict[str, ContextSourcePackage] = {}
    for package in packages:
        binding = context_source_package_binding(package)
        expected = declared.get(binding.package_sha256)
        if expected is None:
            raise ValueError(
                "native source package is not referenced by the supplied proposals: "
                f"{binding.package_sha256}"
            )
        if binding != expected:
            raise ValueError("native source package differs from its proposal source binding")
        if binding.package_sha256 in package_by_hash:
            raise ValueError("native source packages must be unique by package hash")
        package_by_hash[binding.package_sha256] = package
    return package_by_hash, set(package_by_hash) == set(declared)


def _native_case_source(
    case: AssertionGoldenCase,
    proposal: DocumentKnowledgeProposal | None,
    package_by_hash: dict[str, ContextSourcePackage],
    *,
    historical_resolver: FrozenSourceResolver | None,
) -> tuple[NativeSourcePackageResolver | None, CandidateSourceComparison]:
    if proposal is None:
        return None, CandidateSourceComparison()
    binding = next(
        (
            item
            for item in proposal.context_source_bindings
            if item.target_clause_id == case.clause_id.value
        ),
        None,
    )
    if binding is None:
        return None, CandidateSourceComparison(
            status=CandidateSourceComparisonStatus.PARTIAL,
            basis="golden_target_body",
        )
    package = package_by_hash.get(binding.package_sha256)
    if package is None:
        return None, CandidateSourceComparison(
            status=CandidateSourceComparisonStatus.PARTIAL,
            basis="golden_target_body",
            candidate_package_sha256=binding.package_sha256,
            candidate_document_revision=binding.document_revision,
        )
    resolver = NativeSourcePackageResolver(package, binding)
    comparison = _compare_candidate_sources(case, resolver, historical_resolver)
    return resolver, comparison


def _compare_candidate_sources(
    case: AssertionGoldenCase,
    resolver: NativeSourcePackageResolver,
    historical: FrozenSourceResolver | None,
) -> CandidateSourceComparison:
    candidate_hashes = resolver.surface_hashes()
    if historical is not None:
        expected_hashes = historical.surface_hashes(source_document_key=case.source_document_key)
        compared = matching = changed = additional = 0
        partial = False
        for key, hashes in candidate_hashes.items():
            expected = tuple(dict.fromkeys(expected_hashes.get(key, ())))
            current = tuple(dict.fromkeys(hashes))
            if not expected:
                additional += 1
                continue
            if len(expected) != 1 or len(current) != 1:
                partial = True
                continue
            compared += 1
            if expected[0] == current[0]:
                matching += 1
            else:
                changed += 1
        if changed:
            status = CandidateSourceComparisonStatus.CHANGED
        elif partial or compared == 0:
            status = CandidateSourceComparisonStatus.PARTIAL
        else:
            status = CandidateSourceComparisonStatus.MATCHING
        return CandidateSourceComparison(
            status=status,
            basis="historical_audit_overlap",
            candidate_package_sha256=resolver.binding.package_sha256,
            candidate_document_revision=resolver.binding.document_revision,
            compared_surfaces=compared,
            matching_surfaces=matching,
            changed_surfaces=changed,
            additional_candidate_surfaces=additional,
        )

    key = FrozenSourceKey(case.source_document_key, case.clause_id.value, EvidenceSourceKind.BODY)
    hashes = tuple(dict.fromkeys(candidate_hashes.get(key, ())))
    additional = len([candidate_key for candidate_key in candidate_hashes if candidate_key != key])
    if len(hashes) != 1:
        return CandidateSourceComparison(
            status=CandidateSourceComparisonStatus.PARTIAL,
            basis="golden_target_body",
            candidate_package_sha256=resolver.binding.package_sha256,
            candidate_document_revision=resolver.binding.document_revision,
            additional_candidate_surfaces=additional,
        )
    changed = int(hashes[0] != case.text_sha256)
    return CandidateSourceComparison(
        status=(
            CandidateSourceComparisonStatus.CHANGED
            if changed
            else CandidateSourceComparisonStatus.MATCHING
        ),
        basis="golden_target_body",
        candidate_package_sha256=resolver.binding.package_sha256,
        candidate_document_revision=resolver.binding.document_revision,
        compared_surfaces=1,
        matching_surfaces=1 - changed,
        changed_surfaces=changed,
        additional_candidate_surfaces=additional,
    )


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
