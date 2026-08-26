"""Qualification of ontology-guided semantic extraction artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_extraction import FormalOntologyVocabulary
from standards_atlas.domain.model import DocumentSemanticExtraction


class SemanticExtractionQualificationConfig(BaseModel):
    """Manifest-owned policy for Slice 4b semantic extraction qualification."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    ontology_versions: tuple[str, ...] = (
        "standards-atlas-core@1.1.0",
        "functional-safety@1.1.0",
    )
    minimum_entity_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    minimum_relation_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    minimum_ontology_conformance: float = Field(default=1.0, ge=0.0, le=1.0)
    gold_path: Path | None = None
    generate_missing: bool = True
    model: str | None = None
    timeout_seconds: float = Field(default=240.0, gt=0.0)


class OntologyViolationSummary(BaseModel):
    """Aggregate count for one rejected ontology term."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    term: str = Field(min_length=1)
    count: int = Field(ge=1)


class SemanticExtractionQualificationReport(BaseModel):
    """Auditable metrics for one set of semantic extraction artifacts."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.3"
    task: str = "formal-semantic-knowledge-extraction"
    ontology_versions: tuple[str, ...]
    extraction_model: str | None = None
    extraction_provider: str | None = None
    extraction_timeout_seconds: float = Field(default=240.0, gt=0.0)
    selected_clause_count: int = Field(default=0, ge=0)
    eligibility_context_clause_count: int = Field(default=0, ge=0)
    eligible_clause_count: int = Field(default=0, ge=0)
    attempted_clause_count: int = Field(default=0, ge=0)
    extracted_clause_count: int = Field(default=0, ge=0)
    skipped_clause_count: int = Field(default=0, ge=0)
    documents: int = Field(ge=0)
    clauses: int = Field(ge=0)
    entities: int = Field(ge=0)
    relations: int = Field(ge=0)
    ontology_conformance: float = Field(ge=0.0, le=1.0)
    ontology_violation_count: int = Field(default=0, ge=0)
    undeclared_class_count: int = Field(default=0, ge=0)
    undeclared_property_count: int = Field(default=0, ge=0)
    invalid_relation_count: int = Field(default=0, ge=0)
    ontology_violations: tuple[OntologyViolationSummary, ...] = ()
    extraction_failure_count: int = Field(default=0, ge=0)
    timeout_count: int = Field(default=0, ge=0)
    response_error_count: int = Field(default=0, ge=0)
    unavailable_count: int = Field(default=0, ge=0)
    extraction_failures: tuple[dict[str, str], ...] = ()
    entity_confidence_pass_rate: float = Field(ge=0.0, le=1.0)
    relation_confidence_pass_rate: float = Field(ge=0.0, le=1.0)
    gold_available: bool = False
    gold_scored_items: int = Field(default=0, ge=0)
    entity_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    relation_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    relation_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    relation_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    passed: bool
    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def metrics(self) -> tuple[float, float, float]:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return precision, recall, f1


def qualify_semantic_extractions(
    extractions: tuple[DocumentSemanticExtraction, ...],
    config: SemanticExtractionQualificationConfig,
    *,
    expected_clause_count: int | None = None,
    selected_clause_count: int | None = None,
    eligibility_context_clause_count: int | None = None,
    eligible_clause_count: int | None = None,
    extraction_model: str | None = None,
    extraction_provider: str | None = None,
) -> SemanticExtractionQualificationReport:
    """Measure ontology conformance, confidence gates, and optional gold agreement."""
    vocabulary = FormalOntologyVocabulary.load(config.ontology_versions)
    entity_total = relation_total = conforming = total_terms = 0
    entity_confident = relation_confident = 0
    violation_counts: dict[tuple[str, str], int] = {}
    invalid_relation_count = 0
    extraction_failures: list[dict[str, str]] = []
    clauses = 0
    for document in extractions:
        extraction_failures.extend(
            {
                "document_key": document.source_document_key,
                "clause_id": failure.clause_id,
                "kind": failure.kind,
                "error_type": failure.error_type,
                "message": failure.message,
            }
            for failure in document.failures
        )
        for clause in document.clauses:
            clauses += 1
            for entity in clause.entities:
                entity_total += 1
                total_terms += 1
                if entity.class_iri.iri in vocabulary.classes:
                    conforming += 1
                if entity.confidence >= config.minimum_entity_confidence:
                    entity_confident += 1
            for relation in clause.relations:
                relation_total += 1
                total_terms += 1
                if relation.predicate.iri in vocabulary.properties:
                    conforming += 1
                if relation.confidence >= config.minimum_relation_confidence:
                    relation_confident += 1
            for violation in clause.violations:
                key = (violation.kind, violation.term)
                violation_counts[key] = violation_counts.get(key, 0) + 1
                if violation.kind in {"undeclared_class", "undeclared_property"}:
                    total_terms += 1
                elif violation.kind == "invalid_relation":
                    invalid_relation_count += 1

    ontology_conformance = conforming / total_terms if total_terms else 1.0
    entity_pass = entity_confident / entity_total if entity_total else 1.0
    relation_pass = relation_confident / relation_total if relation_total else 1.0
    selected_count = (
        selected_clause_count
        if selected_clause_count is not None
        else expected_clause_count
        if expected_clause_count is not None
        else clauses
    )
    context_count = (
        eligibility_context_clause_count
        if eligibility_context_clause_count is not None
        else selected_count
    )
    eligible_count = eligible_clause_count if eligible_clause_count is not None else selected_count
    skipped_count = max(selected_count - eligible_count, 0)
    failures: list[str] = []
    if selected_count > 0 and context_count < selected_count:
        failures.append(
            "qualification eligibility context missing for "
            f"{selected_count - context_count} of {selected_count} selected clauses"
        )
    failed_clause_count = len(extraction_failures)
    attempted_clause_count = clauses + failed_clause_count
    if eligible_count > 0 and attempted_clause_count == 0:
        failures.append(
            "no semantic extractions were produced for "
            f"{eligible_count} eligible qualification clauses"
        )
    if failed_clause_count:
        failures.append(
            f"semantic extraction failed for {failed_clause_count} of "
            f"{eligible_count} eligible qualification clauses"
        )
    if ontology_conformance < config.minimum_ontology_conformance:
        failures.append(
            f"ontology conformance {ontology_conformance:.4f} < "
            f"{config.minimum_ontology_conformance:.4f}"
        )

    gold_available = False
    gold_scored = 0
    entity_metrics: tuple[float, float, float] | None = None
    relation_metrics: tuple[float, float, float] | None = None
    if config.gold_path is not None and config.gold_path.is_file():
        gold_available = True
        gold = yaml.safe_load(config.gold_path.read_text(encoding="utf-8")) or {}
        entity_counts, relation_counts, gold_scored = _score_gold(extractions, gold)
        entity_metrics = entity_counts.metrics()
        relation_metrics = relation_counts.metrics()

    violation_summaries = tuple(
        OntologyViolationSummary(kind=kind, term=term, count=count)
        for (kind, term), count in sorted(violation_counts.items())
    )
    undeclared_class_count = sum(
        item.count for item in violation_summaries if item.kind == "undeclared_class"
    )
    undeclared_property_count = sum(
        item.count for item in violation_summaries if item.kind == "undeclared_property"
    )

    return SemanticExtractionQualificationReport(
        ontology_versions=config.ontology_versions,
        extraction_model=extraction_model,
        extraction_provider=extraction_provider,
        extraction_timeout_seconds=config.timeout_seconds,
        selected_clause_count=selected_count,
        eligibility_context_clause_count=context_count,
        eligible_clause_count=eligible_count,
        attempted_clause_count=attempted_clause_count,
        extracted_clause_count=clauses,
        skipped_clause_count=skipped_count,
        documents=len(extractions),
        clauses=clauses,
        entities=entity_total,
        relations=relation_total,
        ontology_conformance=ontology_conformance,
        ontology_violation_count=sum(item.count for item in violation_summaries),
        undeclared_class_count=undeclared_class_count,
        undeclared_property_count=undeclared_property_count,
        invalid_relation_count=invalid_relation_count,
        ontology_violations=violation_summaries,
        extraction_failure_count=failed_clause_count,
        timeout_count=sum(item["kind"] == "timeout" for item in extraction_failures),
        response_error_count=sum(item["kind"] == "response_error" for item in extraction_failures),
        unavailable_count=sum(item["kind"] == "unavailable" for item in extraction_failures),
        extraction_failures=tuple(extraction_failures),
        entity_confidence_pass_rate=entity_pass,
        relation_confidence_pass_rate=relation_pass,
        gold_available=gold_available,
        gold_scored_items=gold_scored,
        entity_precision=None if entity_metrics is None else entity_metrics[0],
        entity_recall=None if entity_metrics is None else entity_metrics[1],
        entity_f1=None if entity_metrics is None else entity_metrics[2],
        relation_precision=None if relation_metrics is None else relation_metrics[0],
        relation_recall=None if relation_metrics is None else relation_metrics[1],
        relation_f1=None if relation_metrics is None else relation_metrics[2],
        passed=not failures,
        failures=tuple(failures),
    )


def _score_gold(
    extractions: tuple[DocumentSemanticExtraction, ...], gold: dict[str, Any]
) -> tuple[_Counts, _Counts, int]:
    predicted_entities: dict[str, set[tuple[str, str]]] = {}
    predicted_relations: dict[str, set[tuple[str, str, str]]] = {}
    for document in extractions:
        for clause in document.clauses:
            labels = {entity.id.iri: entity.label.strip().casefold() for entity in clause.entities}
            predicted_entities[clause.clause_id] = {
                (entity.class_iri.iri, entity.label.strip().casefold())
                for entity in clause.entities
            }
            predicted_relations[clause.clause_id] = {
                (
                    labels[relation.subject_id.iri],
                    relation.predicate.iri,
                    labels[relation.object_id.iri],
                )
                for relation in clause.relations
            }

    entity = _Counts()
    relation = _Counts()
    scored = 0
    for case in gold.get("cases", []):
        if case.get("status", "published") != "published":
            continue
        clause_id = str(case["clause_id"])
        expected_entities = {
            (str(item["class_iri"]), str(item["label"]).strip().casefold())
            for item in case.get("entities", [])
        }
        expected_relations = {
            (
                str(item["subject_label"]).strip().casefold(),
                str(item["predicate"]),
                str(item["object_label"]).strip().casefold(),
            )
            for item in case.get("relations", [])
        }
        pe = predicted_entities.get(clause_id, set())
        pr = predicted_relations.get(clause_id, set())
        entity = _Counts(
            entity.tp + len(pe & expected_entities),
            entity.fp + len(pe - expected_entities),
            entity.fn + len(expected_entities - pe),
        )
        relation = _Counts(
            relation.tp + len(pr & expected_relations),
            relation.fp + len(pr - expected_relations),
            relation.fn + len(expected_relations - pr),
        )
        scored += 1
    return entity, relation, scored
