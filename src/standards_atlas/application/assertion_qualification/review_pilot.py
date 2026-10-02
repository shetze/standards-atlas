"""Slice-7D pilot selection, proposal projection and golden-suite publication."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from standards_atlas.application.assertion_qualification.audit import (
    AssertionReviewAudit,
    review_case_source_sha256,
)
from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCascadeClauseReport,
    AssertionCascadeRoute,
    AssertionQualificationCascadeReport,
)
from standards_atlas.application.assertion_qualification.evaluation import proposal_sha256
from standards_atlas.application.assertion_qualification.models import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenSuite,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)
from standards_atlas.application.assertion_qualification.projection import project_native_proposal
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    ApplicabilitySelectionCase,
    ApplicabilitySelectionCorpus,
    AssertionReviewApplicabilitySource,
    AssertionReviewCase,
    AssertionReviewEvidenceSpan,
    AssertionReviewPilot,
    AssertionReviewProposalSnapshot,
    AssertionReviewSelection,
    AssertionReviewSourceCorpus,
    AssertionReviewTargetSuite,
    _review_evidence_source_text,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    assertion_cbox_context,
    display_clause_reference,
    proposal_extraction_eligibility,
)
from standards_atlas.domain.model import (
    CanonicalDocumentSection,
    Clause,
    ClauseId,
    DocumentKnowledgeProposal,
    DocumentStructure,
    EngineeringDocument,
)


@dataclass(frozen=True)
class AssertionReviewPilotBuildRequest:
    """Explicit immutable parameters for one pilot review build."""

    review_id: str
    review_version: str
    target_suite: AssertionReviewTargetSuite
    source_corpus_sha256: str
    limit: int = 20
    clause_ids: tuple[str, ...] = ()


def select_applicability_pilot_cases(
    corpus: ApplicabilitySelectionCorpus,
    *,
    limit: int = 20,
    clause_ids: Sequence[str] = (),
    documents: Mapping[str, EngineeringDocument] | None = None,
) -> tuple[ApplicabilitySelectionCase, ...]:
    """Select deterministic published clauses without reusing applicability as assertion gold."""
    published = tuple(
        case
        for case in corpus.cases
        if case.status == "published" and case.expected is not None and case.provenance is not None
    )
    if not published:
        raise ValueError("applicability selection corpus contains no published cases")

    if clause_ids:
        requested = tuple(clause_ids)
        if len(requested) != len(set(requested)):
            raise ValueError("explicit assertion pilot clause ids must be unique")
        by_id: dict[str, ApplicabilitySelectionCase] = {}
        duplicates: set[str] = set()
        for case in published:
            if case.clause_id in by_id:
                duplicates.add(case.clause_id)
            by_id[case.clause_id] = case
        ambiguous = sorted(set(requested) & duplicates)
        if ambiguous:
            raise ValueError(f"explicit assertion pilot clause ids are ambiguous: {ambiguous!r}")
        missing = [clause_id for clause_id in requested if clause_id not in by_id]
        if missing:
            raise ValueError(
                f"assertion pilot clause ids are not published gold cases: {missing!r}"
            )
        return tuple(by_id[clause_id] for clause_id in requested)

    if limit <= 0:
        raise ValueError("assertion review pilot limit must be greater than zero")
    scoped = published
    if documents is not None:
        scoped = tuple(
            case for case in published if _case_is_in_assertion_review_scope(case, documents)
        )
        if not scoped:
            raise ValueError("applicability selection corpus contains no in-scope assertion cases")
    return _stratified_selection(scoped, limit=min(limit, len(scoped)))


def build_assertion_review_pilot(
    corpus: ApplicabilitySelectionCorpus,
    selected_cases: Sequence[ApplicabilitySelectionCase],
    documents: Mapping[str, EngineeringDocument],
    request: AssertionReviewPilotBuildRequest,
) -> AssertionReviewPilot:
    """Bind selected source cases to current EngineeringDocument clause text."""
    if not selected_cases:
        raise ValueError("assertion review pilot requires at least one selected case")

    review_cases: list[AssertionReviewCase] = []
    for source_case in selected_cases:
        document = documents.get(source_case.document_key)
        if document is None:
            raise ValueError(
                f"assertion review source document is not available: {source_case.document_key!r}"
            )
        clause = _clause_by_id(document, source_case.clause_id)
        _validate_source_case(source_case, document, clause)
        assert source_case.expected is not None
        assert source_case.provenance is not None
        text = clause.plain_text
        source_text_sha256 = hashlib.sha256(source_case.text.encode("utf-8")).hexdigest()
        current_text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        review_cases.append(
            AssertionReviewCase(
                clause_id=source_case.clause_id,
                document_key=source_case.document_key,
                reference=source_case.reference,
                canonical_reference=display_clause_reference(document.key.value, clause.reference),
                text=text,
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                applicability_source=AssertionReviewApplicabilitySource(
                    category=source_case.category,
                    present=source_case.expected.present,
                    source_archive=source_case.provenance.source_archive,
                    source_archive_sha256=source_case.provenance.source_archive_sha256,
                    selection_text_sha256=source_text_sha256,
                    selection_text_matches_current=(source_text_sha256 == current_text_sha256),
                ),
                context=assertion_cbox_context(document, clause),
            )
        )

    strategy = "explicit" if request.clause_ids else "stratified"
    selection = AssertionReviewSelection(
        strategy=strategy,
        requested_limit=None if strategy == "explicit" else request.limit,
        selected_clause_ids=tuple(case.clause_id for case in review_cases),
    )
    return AssertionReviewPilot(
        review_id=request.review_id,
        review_version=request.review_version,
        target_suite=request.target_suite,
        source_corpus=AssertionReviewSourceCorpus(
            corpus_id=corpus.corpus_id,
            corpus_version=corpus.corpus_version,
            corpus_sha256=request.source_corpus_sha256,
        ),
        selection=selection,
        cases=tuple(review_cases),
    )


def attach_cascade_to_assertion_review_pilot(
    review: AssertionReviewPilot,
    *,
    cascade: AssertionQualificationCascadeReport,
    efficient: DocumentKnowledgeProposal,
    escalation: DocumentKnowledgeProposal | None,
) -> AssertionReviewPilot:
    """Attach one document's final Slice-7B candidates without changing human annotations."""
    _validate_cascade_inputs(review, cascade=cascade, efficient=efficient, escalation=escalation)
    clause_reports = {item.clause_id.value: item for item in cascade.clauses}
    updated: list[AssertionReviewCase] = []
    matched = 0
    for case in review.cases:
        if case.document_key != cascade.source_document_key:
            updated.append(case)
            continue
        clause_report = clause_reports.get(case.clause_id)
        if clause_report is None:
            raise ValueError(
                f"cascade report does not contain selected review clause {case.clause_id!r}"
            )
        proposal = (
            efficient
            if clause_report.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED
            else escalation
        )
        if proposal is None:
            raise ValueError(
                f"escalated review clause {case.clause_id!r} requires escalation proposal"
            )
        snapshot = _proposal_snapshot(cascade, clause_report, proposal)
        updated.append(case.model_copy(update={"proposal": snapshot}))
        matched += 1
    if matched == 0:
        raise ValueError(
            f"assertion review pilot contains no cases for document {cascade.source_document_key!r}"
        )
    return review.model_copy(update={"cases": tuple(updated)})


def review_clause_ids(
    review: AssertionReviewPilot,
    *,
    document_key: str,
) -> tuple[str, ...]:
    """Return the exact pilot clause selection for one cascade document run."""
    clause_ids = tuple(case.clause_id for case in review.cases if case.document_key == document_key)
    if not clause_ids:
        raise ValueError(f"assertion review pilot has no cases for document {document_key!r}")
    return clause_ids


def validate_assertion_review_pilot_document(
    review: AssertionReviewPilot,
    document: EngineeringDocument,
) -> tuple[str, ...]:
    """Reconfirm the pilot source binding before running a cascade against a document."""
    cases = tuple(case for case in review.cases if case.document_key == document.key.value)
    if not cases:
        raise ValueError(f"assertion review pilot has no cases for document {document.key.value!r}")
    for case in cases:
        clause = _clause_by_id(document, case.clause_id)
        current_text = clause.plain_text
        current_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
        if current_hash != case.text_sha256 or current_text != case.text:
            raise ValueError(
                f"assertion review pilot source text changed for clause {case.clause_id!r}"
            )
        expected_reference = f"{document.key.value}:{clause.reference.clause}"
        if _reference_key(case.reference) != _reference_key(expected_reference):
            raise ValueError(
                f"assertion review pilot source reference changed for clause {case.clause_id!r}"
            )
        if case.context and case.context != assertion_cbox_context(document, clause):
            raise ValueError(
                f"assertion review pilot CBox context changed for clause {case.clause_id!r}"
            )
    return tuple(case.clause_id for case in cases)


def publish_assertion_review_pilot(audit: AssertionReviewAudit) -> AssertionGoldenSuite:
    """Publish unchanged local expectations from a complete byte-bound audit."""
    review = audit.review
    return AssertionGoldenSuite(
        id=review.target_suite.id,
        version=review.target_suite.version,
        partition=review.target_suite.partition,
        audit=AssertionAuditBinding(
            review_id=review.review_id,
            review_version=review.review_version,
            audit_sha256=audit.audit_sha256,
        ),
        ontology_versions=review.target_suite.ontology_versions,
        cases=tuple(_publish_clause_case(case) for case in review.cases),
    )


_EXCLUDED_ASSERTION_SECTIONS = frozenset(
    {
        CanonicalDocumentSection.FRONT_MATTER,
        CanonicalDocumentSection.REFERENCES,
        CanonicalDocumentSection.BIBLIOGRAPHY,
        CanonicalDocumentSection.BACK_MATTER,
    }
)
_EXCLUDED_ASSERTION_STRUCTURES = frozenset(
    {
        DocumentStructure.FRONT_MATTER,
        DocumentStructure.FOREWORD,
        DocumentStructure.REFERENCES,
        DocumentStructure.BIBLIOGRAPHY,
        DocumentStructure.BACK_MATTER,
    }
)


def _case_is_in_assertion_review_scope(
    case: ApplicabilitySelectionCase,
    documents: Mapping[str, EngineeringDocument],
) -> bool:
    document = documents.get(case.document_key)
    if document is None:
        raise ValueError(f"assertion review scope document is not available: {case.document_key!r}")
    clause = _clause_by_id(document, case.clause_id)
    if not proposal_extraction_eligibility(clause).eligible:
        return False
    by_id = {item.id.value: item for item in document.clauses}
    current: Clause | None = clause
    seen: set[str] = set()
    while current is not None and current.id.value not in seen:
        seen.add(current.id.value)
        profile = current.structural_profile
        if profile is not None and profile.canonical_section in _EXCLUDED_ASSERTION_SECTIONS:
            return False
        structure = current.document_structure
        if structure is not None:
            if structure.category in _EXCLUDED_ASSERTION_STRUCTURES:
                return False
            if (
                structure.category is DocumentStructure.ANNEX
                and (structure.annex_identifier or "").strip().casefold() == "zz"
            ):
                return False
        # Annex ZZ is standardized back matter in CENELEC standards. Keep this
        # address fallback because older deterministic structure classifications may
        # not yet carry an annex_identifier on every descendant.
        root_reference = current.reference.clause.split(".", 1)[0].strip().casefold()
        if root_reference == "zz":
            return False
        parent_id = current.parent_id.value if current.parent_id is not None else None
        current = by_id.get(parent_id) if parent_id is not None else None
    return True


def _stratified_selection(
    cases: Sequence[ApplicabilitySelectionCase], *, limit: int
) -> tuple[ApplicabilitySelectionCase, ...]:
    strata: dict[tuple[bool, str], list[ApplicabilitySelectionCase]] = defaultdict(list)
    for case in cases:
        assert case.expected is not None
        strata[(case.expected.present, case.category)].append(case)

    queues: dict[tuple[bool, str], deque[ApplicabilitySelectionCase]] = {}
    for key, values in strata.items():
        queues[key] = deque(_document_round_robin(values))

    stratum_keys = sorted(queues, key=lambda key: (not key[0], key[1]))
    selected: list[ApplicabilitySelectionCase] = []
    while len(selected) < limit:
        progressed = False
        for key in stratum_keys:
            queue = queues[key]
            if not queue:
                continue
            selected.append(queue.popleft())
            progressed = True
            if len(selected) == limit:
                break
        if not progressed:
            break
    return tuple(selected)


def _document_round_robin(
    cases: Sequence[ApplicabilitySelectionCase],
) -> tuple[ApplicabilitySelectionCase, ...]:
    by_document: dict[str, deque[ApplicabilitySelectionCase]] = defaultdict(deque)
    for case in sorted(cases, key=lambda item: (item.document_key, item.reference, item.clause_id)):
        by_document[case.document_key].append(case)
    documents = sorted(by_document)
    ordered: list[ApplicabilitySelectionCase] = []
    while any(by_document.values()):
        for document_key in documents:
            if by_document[document_key]:
                ordered.append(by_document[document_key].popleft())
    return tuple(ordered)


def _validate_source_case(
    source_case: ApplicabilitySelectionCase,
    document: EngineeringDocument,
    clause: Clause,
) -> None:
    if source_case.document_key != document.key.value:
        raise ValueError("assertion review source document key does not match EngineeringDocument")
    expected_reference = f"{document.key.value}:{clause.reference.clause}"
    if _reference_key(source_case.reference) != _reference_key(expected_reference):
        raise ValueError(
            "assertion review source reference does not match current clause: "
            f"{source_case.reference!r} != {expected_reference!r}"
        )


def _reference_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _clause_by_id(document: EngineeringDocument, clause_id: str) -> Clause:
    for clause in document.clauses:
        if clause.id.value == clause_id:
            return clause
    raise ValueError(
        f"assertion review source clause {clause_id!r} is not present in {document.key.value!r}"
    )


def _validate_cascade_inputs(
    review: AssertionReviewPilot,
    *,
    cascade: AssertionQualificationCascadeReport,
    efficient: DocumentKnowledgeProposal,
    escalation: DocumentKnowledgeProposal | None,
) -> None:
    if cascade.ontology_versions != review.target_suite.ontology_versions:
        raise ValueError("cascade ontology versions do not match assertion review target suite")
    if efficient.source_document_key != cascade.source_document_key:
        raise ValueError("efficient proposal document does not match cascade report")
    if efficient.ontology_versions != cascade.ontology_versions:
        raise ValueError("efficient proposal ontology versions do not match cascade report")
    sources = {source.stage: source for source in cascade.proposal_sources}
    efficient_source = sources["efficient"]
    if efficient.proposal_run_id != efficient_source.proposal_run_id:
        raise ValueError("efficient proposal run id does not match cascade report")
    if proposal_sha256(efficient) != efficient_source.proposal_hash:
        raise ValueError("efficient proposal hash does not match cascade report")

    escalation_source = sources.get("escalation")
    if escalation_source is None:
        if escalation is not None:
            raise ValueError("cascade report has no escalation source for supplied proposal")
    else:
        if escalation is None:
            raise ValueError("cascade report requires an escalation proposal")
        if escalation.source_document_key != cascade.source_document_key:
            raise ValueError("escalation proposal document does not match cascade report")
        if escalation.ontology_versions != cascade.ontology_versions:
            raise ValueError("escalation proposal ontology versions do not match cascade report")
        if escalation.proposal_run_id != escalation_source.proposal_run_id:
            raise ValueError("escalation proposal run id does not match cascade report")
        if proposal_sha256(escalation) != escalation_source.proposal_hash:
            raise ValueError("escalation proposal hash does not match cascade report")

    selected_ids = set(review_clause_ids(review, document_key=cascade.source_document_key))
    cascade_ids = {item.clause_id.value for item in cascade.clauses}
    if selected_ids != cascade_ids:
        raise ValueError(
            "cascade clause selection does not exactly match assertion review pilot: "
            f"review={sorted(selected_ids)!r}, cascade={sorted(cascade_ids)!r}"
        )


def _proposal_snapshot(
    cascade: AssertionQualificationCascadeReport,
    clause_report: AssertionCascadeClauseReport,
    proposal: DocumentKnowledgeProposal,
) -> AssertionReviewProposalSnapshot:
    clause_id = clause_report.clause_id.value
    candidate = project_native_proposal(proposal, clause_id)
    verification = clause_report.verification
    verifier_dispositions: dict[str, str] = {}
    if verification is not None:
        verifier_dispositions = {
            item.candidate_id: item.disposition.value
            for item in (*verification.entity_reviews, *verification.assertion_reviews)
        }
    stage = (
        "efficient"
        if clause_report.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED
        else "escalation"
    )
    return AssertionReviewProposalSnapshot(
        cascade_run_id=cascade.cascade_run_id,
        route=clause_report.route.value,
        reasons=tuple(reason.value for reason in clause_report.reasons),
        proposal_stage=stage,
        proposal_run_id=proposal.proposal_run_id,
        proposal_sha256=proposal_sha256(proposal),
        verifier_dispositions=verifier_dispositions,
        missing_entity_detected=(
            verification.missing_entity_detected if verification is not None else False
        ),
        missing_assertion_detected=(
            verification.missing_assertion_detected if verification is not None else False
        ),
        entities=candidate.entities,
        assertions=candidate.assertions,
        violations=candidate.violations,
        failures=candidate.failures,
        source_package_binding=next(
            (
                binding
                for binding in proposal.context_source_bindings
                if binding.target_clause_id == clause_id
            ),
            None,
        ),
    )


def _publish_review_evidence_span(
    case: AssertionReviewCase, span: AssertionReviewEvidenceSpan
) -> GoldenEvidenceSpan:
    # The review model validator has already established that this exact source surface is
    # present in the fixed review context. Re-resolve it here to derive the Golden hash without
    # copying or normalizing source text.
    source_text = _review_evidence_source_text(case, span)
    if source_text is None:  # pragma: no cover - protected by model validation
        raise ValueError("review evidence source disappeared before publication")
    source_clause_id = span.source_clause_id or case.clause_id
    return GoldenEvidenceSpan(
        source_document_key=case.document_key,
        clause_id=ClauseId(value=source_clause_id),
        source_kind=span.source_kind,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        content_hash=hashlib.sha256(
            source_text[span.start_offset : span.end_offset].encode("utf-8")
        ).hexdigest(),
    )


def _publish_clause_case(case: AssertionReviewCase) -> AssertionGoldenCase:
    assert case.expected is not None  # enforced by the byte-bound audit loader
    return AssertionGoldenCase(
        source_document_key=case.document_key,
        clause_id=ClauseId(value=case.clause_id),
        reference=case.reference,
        canonical_reference=case.canonical_reference,
        text_sha256=case.text_sha256,
        source_sha256=review_case_source_sha256(case),
        entities=tuple(
            GoldenKnowledgeEntity(
                id=entity.id,
                class_iri=entity.class_iri,
                normalized_label=entity.normalized_label,
            )
            for entity in case.expected.entities
        ),
        assertions=tuple(
            GoldenNormativeAssertion(
                id=assertion.id,
                source_clause_id=ClauseId(value=case.clause_id),
                subject_id=assertion.subject_id,
                predicate=assertion.predicate,
                object=assertion.object,
                normative_force=assertion.normative_force,
                evidence=tuple(
                    _publish_review_evidence_span(case, span) for span in assertion.evidence
                ),
            )
            for assertion in case.expected.assertions
        ),
    )
