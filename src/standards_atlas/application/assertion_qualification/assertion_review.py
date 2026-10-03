"""Source-first AP03 assertion HITL contracts and local persistence.

This is a task-specific use case hosted by the existing review workbench.  Model proposals are
read-only preparation.  Only decisions made through a server-bound human view can become publishable
expected knowledge; neither booleans nor model payloads are publication authority by themselves.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.models import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionReviewAssertion,
    AssertionReviewEntity,
    AssertionReviewEvidenceSpan,
    AssertionReviewExpected,
    AssertionReviewProposalSnapshot,
)
from standards_atlas.application.context.input_binding import ContextSourcePackage
from standards_atlas.domain.model import ClauseId, EvidenceSourceKind


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


class ReviewOntologyOption(_Frozen):
    iri: str = Field(min_length=1)
    label: str = Field(min_length=1)


class AssertionReviewSurface(_Frozen):
    source_ref: str = Field(min_length=1)
    source_clause_id: str = Field(min_length=1)
    source_kind: EvidenceSourceKind
    label: str = Field(min_length=1)
    text: str
    start_offset: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AssertionReviewWorkbenchCase(_Frozen):
    case_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    partition: AssertionGoldenPartition
    source_group: str = Field(min_length=1)
    source_package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    surfaces: tuple[AssertionReviewSurface, ...] = Field(min_length=1)
    proposal: AssertionReviewProposalSnapshot | None = None

    @model_validator(mode="after")
    def target_surface_present(self):
        if not any(s.source_clause_id == self.clause_id for s in self.surfaces):
            raise ValueError("assertion review case must expose at least one target-clause source")
        return self


class AssertionReviewWorkbenchPackage(_Frozen):
    contract_id: Literal["assertion-review-workbench-v1"] = "assertion-review-workbench-v1"
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    corpus_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...] = Field(min_length=1)
    class_options: tuple[ReviewOntologyOption, ...] = Field(min_length=1)
    predicate_options: tuple[ReviewOntologyOption, ...] = Field(min_length=1)
    cases: tuple[AssertionReviewWorkbenchCase, ...] = Field(min_length=1)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identities_are_unique(self):
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("assertion review workbench case ids must be unique")
        return self


class EvidenceSelectionInput(_Frozen):
    source_ref: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    prefix: str = ""
    suffix: str = ""


class ReviewEntityInput(_Frozen):
    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)
    evidence: tuple[EvidenceSelectionInput, ...] = ()


class ReviewAssertionInput(_Frozen):
    id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: dict[str, Any]
    normative_force: str = "unspecified"
    evidence: tuple[EvidenceSelectionInput, ...] = Field(min_length=1)


class AssertionHumanDecisionInput(_Frozen):
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    proposal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    entities: tuple[ReviewEntityInput, ...] = ()
    assertions: tuple[ReviewAssertionInput, ...] = ()
    explicit_empty: bool = False
    comment: str = ""

    @model_validator(mode="after")
    def decision_shape(self):
        if self.status == "confirmed" and not self.proposal_sha256:
            raise ValueError("confirmation must bind the visible proposal")
        if self.status in {"deferred", "rejected"} and (self.entities or self.assertions):
            raise ValueError("open/rejected decisions cannot carry expected knowledge")
        if self.status == "corrected" and not (
            self.entities or self.assertions or self.explicit_empty
        ):
            raise ValueError("corrected empty knowledge must be explicitly confirmed empty")
        if self.explicit_empty and (self.entities or self.assertions):
            raise ValueError("explicit empty cannot be combined with entities/assertions")
        return self


class EntityEvidenceRecord(_Frozen):
    entity_id: str
    evidence: tuple[GoldenEvidenceSpan, ...] = ()


class AssertionHumanDecision(_Frozen):
    revision: int = Field(ge=1)
    case_id: str
    reviewer: str = Field(min_length=1)
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    proposal_sha256: str | None = None
    expected: AssertionReviewExpected | None = None
    entity_evidence: tuple[EntityEvidenceRecord, ...] = ()
    explicit_empty: bool = False
    comment: str = ""
    reviewed_at: datetime
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssertionReviewWorkbenchState(_Frozen):
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=0)
    decisions: tuple[AssertionHumanDecision, ...] = ()
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def package_from_cases(
    *,
    id: str,
    version: str,
    corpus_plan_sha256: str,
    ontology_versions: tuple[str, ...],
    class_options: tuple[ReviewOntologyOption, ...],
    predicate_options: tuple[ReviewOntologyOption, ...],
    cases: tuple[AssertionReviewWorkbenchCase, ...],
) -> AssertionReviewWorkbenchPackage:
    body = dict(
        id=id,
        version=version,
        corpus_plan_sha256=corpus_plan_sha256,
        ontology_versions=ontology_versions,
        class_options=class_options,
        predicate_options=predicate_options,
        cases=cases,
    )
    raw = {
        key: (
            [item.model_dump(mode="json") for item in value]
            if isinstance(value, tuple) and value and isinstance(value[0], BaseModel)
            else value
        )
        for key, value in body.items()
    }
    raw["ontology_versions"] = list(ontology_versions)
    raw["contract_id"] = "assertion-review-workbench-v1"
    return AssertionReviewWorkbenchPackage(**body, package_sha256=_digest(raw))


def case_from_source_package(
    package: ContextSourcePackage,
    *,
    partition: AssertionGoldenPartition,
    source_group: str,
    proposal: AssertionReviewProposalSnapshot | None = None,
) -> AssertionReviewWorkbenchCase:
    surfaces = tuple(
        AssertionReviewSurface(
            source_ref=s.package_source_ref,
            source_clause_id=s.source_ref.clause_id,
            source_kind=s.source_ref.source_kind,
            label=s.rendering_id,
            text=s.text,
            start_offset=s.start_offset,
            content_hash=s.content_sha256,
        )
        for s in package.input_surfaces
    )
    return AssertionReviewWorkbenchCase(
        case_id=f"{package.document_key}:{package.target_clause_id}",
        document_key=package.document_key,
        clause_id=package.target_clause_id,
        reference=package.target_reference,
        partition=partition,
        source_group=source_group,
        source_package_sha256="sha256:" + _digest(package.model_dump(mode="json")),
        surfaces=surfaces,
        proposal=proposal,
    )


def initial_assertion_review_state(
    package: AssertionReviewWorkbenchPackage,
) -> AssertionReviewWorkbenchState:
    body = {"package_sha256": package.package_sha256, "revision": 0, "decisions": []}
    return AssertionReviewWorkbenchState(**body, state_sha256=_digest(body))


def _resolve_selection(
    case: AssertionReviewWorkbenchCase, selection: EvidenceSelectionInput
) -> GoldenEvidenceSpan:
    surface = next((s for s in case.surfaces if s.source_ref == selection.source_ref), None)
    if surface is None:
        raise ValueError(f"unknown evidence source_ref: {selection.source_ref}")
    matches = []
    start = 0
    while True:
        index = surface.text.find(selection.quote, start)
        if index < 0:
            break
        before = (
            surface.text[max(0, index - len(selection.prefix)) : index] if selection.prefix else ""
        )
        after_start = index + len(selection.quote)
        after = (
            surface.text[after_start : after_start + len(selection.suffix)]
            if selection.suffix
            else ""
        )
        if (not selection.prefix or before == selection.prefix) and (
            not selection.suffix or after == selection.suffix
        ):
            matches.append(index)
        start = index + 1
    if len(matches) != 1:
        raise ValueError(
            "evidence quote must resolve uniquely on "
            f"{selection.source_ref}; found {len(matches)} matches"
        )
    local = matches[0]
    absolute_start = surface.start_offset + local
    absolute_end = absolute_start + len(selection.quote)
    return GoldenEvidenceSpan(
        source_document_key=case.document_key,
        clause_id=ClauseId(value=surface.source_clause_id),
        source_kind=surface.source_kind,
        start_offset=absolute_start,
        end_offset=absolute_end,
        content_hash=hashlib.sha256(selection.quote.encode("utf-8")).hexdigest(),
    )


def _expected_from_input(
    package: AssertionReviewWorkbenchPackage,
    case: AssertionReviewWorkbenchCase,
    decision: AssertionHumanDecisionInput,
) -> tuple[AssertionReviewExpected | None, tuple[EntityEvidenceRecord, ...]]:
    if decision.status in {"deferred", "rejected"}:
        return None, ()
    if decision.status == "confirmed":
        if case.proposal is None or case.proposal.proposal_sha256 != decision.proposal_sha256:
            raise ValueError("confirmed proposal is not the visible bound proposal")
        entities = tuple(
            AssertionReviewEntity(
                id=entity.id,
                class_iri=entity.class_iri,
                normalized_label=entity.normalized_label,
            )
            for entity in case.proposal.entities
        )
        assertions = []
        # Proposal evidence already carries canonical coordinates; human confirmation
        # may publish it.
        for a in case.proposal.assertions:
            spans = tuple(
                AssertionReviewEvidenceSpan(
                    source_clause_id=evidence.source_clause_id,
                    source_kind=evidence.source_kind,
                    start_offset=evidence.start_offset,
                    end_offset=evidence.end_offset,
                )
                for evidence in a.evidence
                if evidence.start_offset is not None and evidence.end_offset is not None
            )
            if not spans:
                raise ValueError("proposal assertion lacks publishable canonical evidence")
            assertions.append(
                AssertionReviewAssertion(
                    id=a.id,
                    subject_id=a.subject_id,
                    predicate=a.predicate,
                    object=a.object,
                    normative_force=a.normative_force,
                    evidence=spans,
                )
            )
        return AssertionReviewExpected(entities=entities, assertions=tuple(assertions)), ()

    classes = {o.iri for o in package.class_options}
    predicates = {o.iri for o in package.predicate_options}
    if any(e.class_iri not in classes for e in decision.entities):
        raise ValueError("entity class must be selected from the bound ontology")
    if any(a.predicate not in predicates for a in decision.assertions):
        raise ValueError("assertion predicate must be selected from the bound ontology")
    entities = tuple(
        AssertionReviewEntity(
            id=entity.id,
            class_iri=entity.class_iri,
            normalized_label=entity.normalized_label,
        )
        for entity in decision.entities
    )
    entity_evidence = tuple(
        EntityEvidenceRecord(
            entity_id=entity.id,
            evidence=tuple(_resolve_selection(case, item) for item in entity.evidence),
        )
        for entity in decision.entities
    )
    assertions = []
    for a in decision.assertions:
        spans = tuple(_resolve_selection(case, s) for s in a.evidence)
        assertions.append(
            AssertionReviewAssertion(
                id=a.id,
                subject_id=a.subject_id,
                predicate=a.predicate,
                object=a.object,
                normative_force=a.normative_force,
                evidence=tuple(
                    AssertionReviewEvidenceSpan(
                        source_clause_id=span.clause_id.value,
                        source_kind=span.source_kind,
                        start_offset=span.start_offset,
                        end_offset=span.end_offset,
                    )
                    for span in spans
                ),
            )
        )
    expected = AssertionReviewExpected(entities=entities, assertions=tuple(assertions))
    return expected, entity_evidence


def record_assertion_human_decision(
    package: AssertionReviewWorkbenchPackage,
    state: AssertionReviewWorkbenchState,
    *,
    case_id: str,
    reviewer: str,
    decision: AssertionHumanDecisionInput,
) -> AssertionReviewWorkbenchState:
    if state.package_sha256 != package.package_sha256:
        raise ValueError("review state belongs to another package")
    case = next((c for c in package.cases if c.case_id == case_id), None)
    if case is None:
        raise ValueError("case is outside the assertion review package")
    if case.partition is AssertionGoldenPartition.HOLDOUT and case.proposal is not None:
        raise ValueError("holdout model proposals are disabled by default")
    expected, entity_evidence = _expected_from_input(package, case, decision)
    revision = state.revision + 1
    body = dict(
        revision=revision,
        case_id=case_id,
        reviewer=reviewer,
        status=decision.status,
        proposal_sha256=decision.proposal_sha256,
        expected=expected,
        entity_evidence=entity_evidence,
        explicit_empty=decision.explicit_empty,
        comment=decision.comment,
        reviewed_at=datetime.now(UTC),
    )
    fingerprint = {
        key: (
            value.model_dump(mode="json")
            if isinstance(value, BaseModel)
            else [item.model_dump(mode="json") for item in value]
            if isinstance(value, tuple)
            else value.isoformat()
            if isinstance(value, datetime)
            else value
        )
        for key, value in body.items()
    }
    entry = AssertionHumanDecision(**body, decision_sha256=_digest(fingerprint))
    decisions = (*state.decisions, entry)
    state_body = {
        "package_sha256": package.package_sha256,
        "revision": revision,
        "decisions": [item.model_dump(mode="json") for item in decisions],
    }
    return AssertionReviewWorkbenchState(**state_body, state_sha256=_digest(state_body))


def active_assertion_decisions(
    state: AssertionReviewWorkbenchState,
) -> dict[str, AssertionHumanDecision]:
    return {decision.case_id: decision for decision in state.decisions}


def publish_confirmed_assertion_suite(
    package: AssertionReviewWorkbenchPackage,
    state: AssertionReviewWorkbenchState,
    *,
    partition: AssertionGoldenPartition,
    suite_id: str,
    suite_version: str,
) -> AssertionGoldenSuite:
    active = active_assertion_decisions(state)
    cases = []
    reviewers = set()
    for case in package.cases:
        if case.partition is not partition:
            continue
        decision = active.get(case.case_id)
        if (
            decision is None
            or decision.status not in {"confirmed", "corrected"}
            or decision.expected is None
        ):
            continue
        reviewers.add(decision.reviewer)
        entities = tuple(
            GoldenKnowledgeEntity(**entity.model_dump()) for entity in decision.expected.entities
        )
        assertions = []
        for assertion in decision.expected.assertions:
            spans = []
            for span in assertion.evidence:
                source = next(
                    surface
                    for surface in case.surfaces
                    if surface.source_clause_id == (span.source_clause_id or case.clause_id)
                    and surface.source_kind == span.source_kind
                )
                quote = source.text[
                    span.start_offset - source.start_offset : span.end_offset - source.start_offset
                ]
                spans.append(
                    GoldenEvidenceSpan(
                        source_document_key=case.document_key,
                        clause_id=ClauseId(value=span.source_clause_id or case.clause_id),
                        source_kind=span.source_kind,
                        start_offset=span.start_offset,
                        end_offset=span.end_offset,
                        content_hash=hashlib.sha256(quote.encode()).hexdigest(),
                    )
                )
            assertions.append(
                GoldenNormativeAssertion(
                    id=assertion.id,
                    source_clause_id=ClauseId(value=case.clause_id),
                    subject_id=assertion.subject_id,
                    predicate=assertion.predicate,
                    object=assertion.object,
                    normative_force=assertion.normative_force,
                    evidence=tuple(spans),
                )
            )
        target = next(
            surface
            for surface in case.surfaces
            if surface.source_clause_id == case.clause_id
            and surface.source_kind is EvidenceSourceKind.BODY
        )
        cases.append(
            AssertionGoldenCase(
                source_document_key=case.document_key,
                clause_id=ClauseId(value=case.clause_id),
                reference=case.reference,
                canonical_reference=case.reference,
                text_sha256=hashlib.sha256(target.text.encode()).hexdigest(),
                source_sha256=case.source_package_sha256.removeprefix("sha256:"),
                entities=entities,
                assertions=tuple(assertions),
            )
        )
    if not cases:
        raise ValueError("no genuinely human-confirmed cases are available for publication")
    audit_hash = _digest(
        {
            "package": package.package_sha256,
            "state": state.state_sha256,
            "reviewers": sorted(reviewers),
            "partition": partition.value,
        }
    )
    return AssertionGoldenSuite(
        id=suite_id,
        version=suite_version,
        partition=partition,
        audit=AssertionAuditBinding(
            review_id=package.id,
            review_version=package.version,
            audit_sha256=audit_hash,
        ),
        ontology_versions=package.ontology_versions,
        cases=tuple(cases),
    )


def write_assertion_review_package(root: Path, package: AssertionReviewWorkbenchPackage) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _atomic_json(root / "assertion-review-package.json", package.model_dump(mode="json"))
    if not (root / "assertion-review-state.json").exists():
        _atomic_json(
            root / "assertion-review-state.json",
            initial_assertion_review_state(package).model_dump(mode="json"),
        )


def load_assertion_review_package(root: Path):
    package = AssertionReviewWorkbenchPackage.model_validate_json(
        (root / "assertion-review-package.json").read_bytes()
    )
    state = AssertionReviewWorkbenchState.model_validate_json(
        (root / "assertion-review-state.json").read_bytes()
    )
    if state.package_sha256 != package.package_sha256:
        raise ValueError("assertion review package/state binding mismatch")
    return package, state


def write_assertion_review_state(root: Path, state: AssertionReviewWorkbenchState) -> None:
    _atomic_json(root / "assertion-review-state.json", state.model_dump(mode="json"))


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
