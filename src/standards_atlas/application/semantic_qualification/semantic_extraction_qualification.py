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


class SemanticExtractionQualificationReport(BaseModel):
    """Auditable metrics for one set of semantic extraction artifacts."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    task: str = "formal-semantic-knowledge-extraction"
    ontology_versions: tuple[str, ...]
    documents: int = Field(ge=0)
    clauses: int = Field(ge=0)
    entities: int = Field(ge=0)
    relations: int = Field(ge=0)
    ontology_conformance: float = Field(ge=0.0, le=1.0)
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
) -> SemanticExtractionQualificationReport:
    """Measure ontology conformance, confidence gates, and optional gold agreement."""
    vocabulary = FormalOntologyVocabulary.load(config.ontology_versions)
    entity_total = relation_total = conforming = total_terms = 0
    entity_confident = relation_confident = 0
    clauses = 0
    for document in extractions:
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

    ontology_conformance = conforming / total_terms if total_terms else 1.0
    entity_pass = entity_confident / entity_total if entity_total else 1.0
    relation_pass = relation_confident / relation_total if relation_total else 1.0
    failures: list[str] = []
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

    return SemanticExtractionQualificationReport(
        ontology_versions=config.ontology_versions,
        documents=len(extractions),
        clauses=clauses,
        entities=entity_total,
        relations=relation_total,
        ontology_conformance=ontology_conformance,
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
