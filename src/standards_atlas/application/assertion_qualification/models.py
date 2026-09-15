"""Schema-1 contracts for assertion-centred golden suites and evaluation reports."""

from __future__ import annotations

import math
import re
import unicodedata
from enum import StrEnum
from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import AssertionObject, ClauseId, NormativeForce

ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION = 1
ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION = 1
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


def _require_absolute_iri(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    scheme = urlsplit(value).scheme
    if not scheme or not _IRI_SCHEME.fullmatch(scheme):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return value


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _validate_ontology_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        raise ValueError("assertion golden suite requires at least one ontology version")
    if len(value) != len(set(value)):
        raise ValueError("assertion golden suite ontology versions must be unique")
    for reference in value:
        if reference != reference.strip() or reference.count("@") != 1:
            raise ValueError("ontology versions must use '<id>@<version>' references")
        ontology_id, version = reference.rsplit("@", 1)
        if not ontology_id or not version:
            raise ValueError("ontology versions must use '<id>@<version>' references")
    return value


class AssertionGoldenPartition(StrEnum):
    """Independent evaluation partition owned by one golden suite."""

    DEVELOPMENT = "development"
    HOLDOUT = "holdout"


class GoldenKnowledgeEntity(BaseModel):
    """Expected ontology-grounded entity independent from runtime proposal IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)

    @field_validator("class_iri")
    @classmethod
    def class_iri_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="golden entity class_iri")


class GoldenEvidenceSpan(BaseModel):
    """Exact expected grounding span in canonical clause plain text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def range_is_non_empty(self) -> GoldenEvidenceSpan:
        if self.end_offset <= self.start_offset:
            raise ValueError("golden evidence end_offset must be greater than start_offset")
        return self


class GoldenNormativeAssertion(BaseModel):
    """Expected relation, force and exact grounding for one source assertion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source_clause_id: ClauseId
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce = NormativeForce.UNSPECIFIED
    evidence: tuple[GoldenEvidenceSpan, ...] = Field(min_length=1)

    @field_validator("predicate")
    @classmethod
    def predicate_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="golden assertion predicate")

    @model_validator(mode="after")
    def evidence_is_local_to_source_clause(self) -> GoldenNormativeAssertion:
        if any(span.clause_id != self.source_clause_id for span in self.evidence):
            raise ValueError("golden assertion evidence must belong to its source clause")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("golden assertion evidence spans must be unique")
        return self


class AssertionGoldenCase(BaseModel):
    """Expected engineering knowledge for one source document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str = Field(min_length=1)
    entities: tuple[GoldenKnowledgeEntity, ...] = ()
    assertions: tuple[GoldenNormativeAssertion, ...] = ()

    @field_validator("source_document_key")
    @classmethod
    def document_key_has_no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("golden source document key must not contain surrounding whitespace")
        return value

    @model_validator(mode="after")
    def assertion_references_are_local(self) -> AssertionGoldenCase:
        entity_ids = [entity.id for entity in self.entities]
        assertion_ids = [assertion.id for assertion in self.assertions]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("golden entity ids must be unique within a document")
        entity_signatures = [
            (_normalize_label(entity.normalized_label), entity.class_iri)
            for entity in self.entities
        ]
        if len(entity_signatures) != len(set(entity_signatures)):
            raise ValueError("golden entities must be semantically unique within a document")
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("golden assertion ids must be unique within a document")
        known_entities = set(entity_ids)
        missing_subjects = {
            assertion.subject_id
            for assertion in self.assertions
            if assertion.subject_id not in known_entities
        }
        if missing_subjects:
            raise ValueError(f"golden assertions reference unknown subjects: {missing_subjects!r}")
        missing_objects = {
            assertion.object.entity_id
            for assertion in self.assertions
            if assertion.object.kind == "entity"
            and assertion.object.entity_id not in known_entities
        }
        if missing_objects:
            raise ValueError(f"golden assertions reference unknown objects: {missing_objects!r}")
        return self


class AssertionGoldenSuite(SchemaBoundModel):
    """Versioned assertion golden suite for one independent evaluation partition."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-golden-suite"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    partition: AssertionGoldenPartition
    ontology_versions: tuple[str, ...]
    cases: tuple[AssertionGoldenCase, ...] = Field(min_length=1)

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def document_keys_are_unique(self) -> AssertionGoldenSuite:
        keys = [case.source_document_key for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("assertion golden suite document keys must be unique")
        return self


class CountMetrics(BaseModel):
    """Precision/recall counts for a multiset comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: int = Field(ge=0)
    predicted: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_and_ratios_are_consistent(self) -> CountMetrics:
        if self.true_positive > min(self.expected, self.predicted):
            raise ValueError("true_positive cannot exceed expected or predicted counts")
        if self.false_positive != self.predicted - self.true_positive:
            raise ValueError("false_positive must equal predicted minus true_positive")
        if self.false_negative != self.expected - self.true_positive:
            raise ValueError("false_negative must equal expected minus true_positive")
        precision = (
            self.true_positive / self.predicted if self.predicted else float(self.expected == 0)
        )
        recall = self.true_positive / self.expected if self.expected else float(self.predicted == 0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        for field_name, actual, expected in (
            ("precision", self.precision, precision),
            ("recall", self.recall, recall),
            ("f1", self.f1, f1),
        ):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"{field_name} is inconsistent with qualification counts")
        return self


class AccuracyMetrics(BaseModel):
    """Accuracy for attributes evaluated only on aligned semantic items."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluated: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> AccuracyMetrics:
        if self.correct > self.evaluated:
            raise ValueError("accuracy correct count cannot exceed evaluated count")
        if self.evaluated == 0 and self.accuracy is not None:
            raise ValueError("accuracy must be None when no items were evaluated")
        if self.evaluated > 0 and self.accuracy is None:
            raise ValueError("accuracy is required when items were evaluated")
        if self.evaluated > 0 and self.accuracy is not None:
            expected = self.correct / self.evaluated
            if not math.isclose(self.accuracy, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("accuracy is inconsistent with evaluated/correct counts")
        return self


class AssertionQualificationCaseReport(BaseModel):
    """Deterministic evaluation result for one golden document case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str
    proposal_run_id: str | None = None
    proposal_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    entities: CountMetrics
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    grounding_accuracy: AccuracyMetrics
    exact_assertion_accuracy: AccuracyMetrics
    entity_false_positive_ids: tuple[str, ...] = ()
    entity_false_negative_ids: tuple[str, ...] = ()
    assertion_false_positive_ids: tuple[str, ...] = ()
    assertion_false_negative_ids: tuple[str, ...] = ()
    proposal_violations: int = Field(default=0, ge=0)
    proposal_failures: int = Field(default=0, ge=0)


class AssertionQualificationAggregate(BaseModel):
    """Aggregate Slice-7A metrics across all golden document cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: int = Field(ge=1)
    entities: CountMetrics
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    grounding_accuracy: AccuracyMetrics
    exact_assertion_accuracy: AccuracyMetrics


class AssertionQualificationProposalSource(BaseModel):
    """Exact proposal artifact identity included in one evaluation report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str
    proposal_run_id: str
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor: str
    extractor_version: str
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None


class AssertionQualificationReport(SchemaBoundModel):
    """Reproducible metric report without an auto-adoption pass/fail policy."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-qualification-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION
    golden_suite_id: str
    golden_suite_version: str
    golden_partition: AssertionGoldenPartition
    golden_suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...]
    proposal_sources: tuple[AssertionQualificationProposalSource, ...] = ()
    cases: tuple[AssertionQualificationCaseReport, ...] = Field(min_length=1)
    aggregate: AssertionQualificationAggregate

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def report_identity_is_consistent(self) -> AssertionQualificationReport:
        if self.aggregate.documents != len(self.cases):
            raise ValueError("aggregate document count must match qualification cases")
        case_keys = [case.source_document_key for case in self.cases]
        if len(case_keys) != len(set(case_keys)):
            raise ValueError("qualification report document keys must be unique")
        source_keys = [source.source_document_key for source in self.proposal_sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("qualification report proposal source keys must be unique")
        source_by_key = {source.source_document_key: source for source in self.proposal_sources}
        if not set(source_by_key) <= set(case_keys):
            raise ValueError("qualification report proposal sources must belong to report cases")
        for case in self.cases:
            source = source_by_key.get(case.source_document_key)
            if source is None:
                if case.proposal_run_id is not None or case.proposal_hash is not None:
                    raise ValueError("case proposal identity requires a proposal source entry")
                continue
            if (case.proposal_run_id, case.proposal_hash) != (
                source.proposal_run_id,
                source.proposal_hash,
            ):
                raise ValueError("case proposal identity does not match proposal source entry")
        return self
