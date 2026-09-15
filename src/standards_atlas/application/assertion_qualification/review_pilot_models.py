"""Schema-1 contracts for the Slice-7D assertion review pilot."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import StrEnum
from typing import ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.assertion_qualification.models import AssertionGoldenPartition
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import AssertionObject, NormativeForce

ASSERTION_REVIEW_PILOT_SCHEMA_VERSION = 1
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


def _require_absolute_iri(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    scheme = urlsplit(value).scheme
    if not scheme or not _IRI_SCHEME.fullmatch(scheme):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return value


def normalize_review_label(value: str) -> str:
    """Return the semantic label normalization shared by review publication."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


class ApplicabilitySelectionExpected(BaseModel):
    """Presence decision imported only as selection provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    present: bool


class ApplicabilitySelectionProvenance(BaseModel):
    """Source qualification archive provenance from the applicability corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_archive: str = Field(min_length=1)
    source_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApplicabilitySelectionCase(BaseModel):
    """One applicability gold case usable as a Slice-7D clause selection source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    text: str
    category: str = Field(min_length=1)
    status: Literal["proposed", "published", "rejected"] = "proposed"
    expected: ApplicabilitySelectionExpected | None = None
    provenance: ApplicabilitySelectionProvenance | None = None

    @model_validator(mode="after")
    def published_cases_have_review_provenance(self) -> ApplicabilitySelectionCase:
        if self.status == "published" and (self.expected is None or self.provenance is None):
            raise ValueError(
                "published applicability selection cases require expected and provenance"
            )
        return self


class ApplicabilitySelectionCorpus(BaseModel):
    """Current applicability golden corpus projected as a read-only selection source."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    source_schema_version: Literal["3.0"] = Field(default="3.0", alias="schema_version")
    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    cases: tuple[ApplicabilitySelectionCase, ...]

    @model_validator(mode="after")
    def case_keys_are_unique(self) -> ApplicabilitySelectionCorpus:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("applicability selection case keys must be unique")
        return self


class AssertionReviewStatus(StrEnum):
    """Human state of one selected assertion review case."""

    PENDING = "pending"
    REVIEWED = "reviewed"


class AssertionReviewSourceCorpus(BaseModel):
    """Immutable identity of the corpus used only to choose pilot clauses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssertionReviewSelection(BaseModel):
    """Reproducible selection metadata for the pilot review set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Literal["stratified", "explicit"]
    requested_limit: int | None = Field(default=None, ge=1)
    selected_clause_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def clause_ids_are_unique(self) -> AssertionReviewSelection:
        if len(self.selected_clause_ids) != len(set(self.selected_clause_ids)):
            raise ValueError("assertion review selection clause ids must be unique")
        if self.strategy == "stratified" and self.requested_limit is None:
            raise ValueError("stratified assertion review selection requires requested_limit")
        return self


class AssertionReviewTargetSuite(BaseModel):
    """Golden-suite identity the completed pilot review will publish."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    partition: AssertionGoldenPartition
    ontology_versions: tuple[str, ...] = Field(min_length=1)

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("assertion review ontology versions must be unique")
        for reference in value:
            if reference != reference.strip() or reference.count("@") != 1:
                raise ValueError("ontology versions must use '<id>@<version>' references")
            ontology_id, version = reference.rsplit("@", 1)
            if not ontology_id or not version:
                raise ValueError("ontology versions must use '<id>@<version>' references")
        return value


class AssertionReviewEvidenceSpan(BaseModel):
    """Reviewer-authored exact evidence offsets inside the selected clause text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    @model_validator(mode="after")
    def range_is_non_empty(self) -> AssertionReviewEvidenceSpan:
        if self.end_offset <= self.start_offset:
            raise ValueError("assertion review evidence end_offset must exceed start_offset")
        return self


class AssertionReviewEntity(BaseModel):
    """Case-local human reference entity before deterministic suite publication."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)

    @field_validator("class_iri")
    @classmethod
    def class_iri_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="assertion review entity class_iri")


class AssertionReviewAssertion(BaseModel):
    """Case-local human assertion annotation with exact clause evidence offsets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce = NormativeForce.UNSPECIFIED
    evidence: tuple[AssertionReviewEvidenceSpan, ...] = Field(min_length=1)

    @field_validator("predicate")
    @classmethod
    def predicate_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="assertion review predicate")

    @model_validator(mode="after")
    def evidence_spans_are_unique(self) -> AssertionReviewAssertion:
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("assertion review evidence spans must be unique")
        return self


class AssertionReviewExpected(BaseModel):
    """Human-reviewed expected knowledge for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entities: tuple[AssertionReviewEntity, ...] = ()
    assertions: tuple[AssertionReviewAssertion, ...] = ()

    @model_validator(mode="after")
    def references_are_case_local(self) -> AssertionReviewExpected:
        entity_ids = [entity.id for entity in self.entities]
        assertion_ids = [assertion.id for assertion in self.assertions]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("assertion review entity ids must be unique within a case")
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("assertion review assertion ids must be unique within a case")
        signatures = [
            (normalize_review_label(entity.normalized_label), entity.class_iri)
            for entity in self.entities
        ]
        if len(signatures) != len(set(signatures)):
            raise ValueError("assertion review entities must be semantically unique within a case")
        known_entities = set(entity_ids)
        missing_subjects = {
            assertion.subject_id
            for assertion in self.assertions
            if assertion.subject_id not in known_entities
        }
        if missing_subjects:
            raise ValueError(
                f"assertion review assertions reference unknown subjects: {missing_subjects!r}"
            )
        missing_objects = {
            assertion.object.entity_id
            for assertion in self.assertions
            if assertion.object.kind == "entity"
            and assertion.object.entity_id not in known_entities
        }
        if missing_objects:
            raise ValueError(
                f"assertion review assertions reference unknown objects: {missing_objects!r}"
            )
        return self


class AssertionReviewApplicabilitySource(BaseModel):
    """Applicability gold metadata retained strictly as selection provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(min_length=1)
    present: bool
    source_archive: str = Field(min_length=1)
    source_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssertionProposalEvidenceSnapshot(BaseModel):
    """Read-only evidence coordinates shown beside a proposal candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor_id: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class AssertionProposalEntitySnapshot(BaseModel):
    """Read-only final-cascade entity suggestion for one review case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
    evidence: tuple[AssertionProposalEvidenceSnapshot, ...] = ()


class AssertionProposalAssertionSnapshot(BaseModel):
    """Read-only final-cascade assertion suggestion for one review case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
    evidence: tuple[AssertionProposalEvidenceSnapshot, ...] = ()


class AssertionReviewProposalSnapshot(BaseModel):
    """Final candidate set selected by one Slice-7B cascade route."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cascade_run_id: str = Field(min_length=1)
    route: Literal["efficient_accepted", "escalated"]
    reasons: tuple[str, ...] = ()
    proposal_stage: Literal["efficient", "escalation"]
    proposal_run_id: str = Field(min_length=1)
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_dispositions: dict[str, str] = Field(default_factory=dict)
    missing_entity_detected: bool = False
    missing_assertion_detected: bool = False
    entities: tuple[AssertionProposalEntitySnapshot, ...] = ()
    assertions: tuple[AssertionProposalAssertionSnapshot, ...] = ()
    violations: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


class AssertionReviewCase(BaseModel):
    """One clause selected for human assertion review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    canonical_reference: str = Field(min_length=1)
    text: str
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applicability_source: AssertionReviewApplicabilitySource
    proposal: AssertionReviewProposalSnapshot | None = None
    review_status: AssertionReviewStatus = AssertionReviewStatus.PENDING
    expected: AssertionReviewExpected | None = None

    @model_validator(mode="after")
    def review_annotation_is_consistent(self) -> AssertionReviewCase:
        actual_text_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if actual_text_hash != self.text_sha256:
            raise ValueError("assertion review case text_sha256 does not match embedded text")
        if self.review_status is AssertionReviewStatus.REVIEWED and self.expected is None:
            raise ValueError("reviewed assertion pilot cases require expected knowledge")
        if self.expected is not None:
            for assertion in self.expected.assertions:
                for span in assertion.evidence:
                    if span.end_offset > len(self.text):
                        raise ValueError(
                            f"assertion review evidence exceeds clause text for {self.clause_id!r}"
                        )
        return self


class AssertionReviewPilot(SchemaBoundModel):
    """Editable pilot review artifact built from verified current document clauses."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-review-pilot"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_REVIEW_PILOT_SCHEMA_VERSION
    review_id: str = Field(min_length=1)
    review_version: str = Field(min_length=1)
    target_suite: AssertionReviewTargetSuite
    source_corpus: AssertionReviewSourceCorpus
    selection: AssertionReviewSelection
    cases: tuple[AssertionReviewCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def cases_match_selection(self) -> AssertionReviewPilot:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("assertion review pilot case keys must be unique")
        clause_ids = tuple(case.clause_id for case in self.cases)
        if clause_ids != self.selection.selected_clause_ids:
            raise ValueError("assertion review pilot cases must match selected_clause_ids in order")
        return self
