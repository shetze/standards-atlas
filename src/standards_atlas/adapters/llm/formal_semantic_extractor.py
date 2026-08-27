"""Structured LLM adapter for ontology-guided concept and relation extraction."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest
from standards_atlas.application.semantic_extraction import (
    FormalOntologyVocabulary,
    display_clause_reference,
    project_clause_content,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseSemanticExtraction,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionProvenance,
    ExtractionViolation,
    SemanticResource,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "relations"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["class_iri", "label", "confidence", "evidence"],
                "properties": {
                    "class_iri": {"type": "string"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {"type": "string"},
                },
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "subject_index",
                    "predicate",
                    "object_index",
                    "confidence",
                    "evidence",
                ],
                "properties": {
                    "subject_index": {"type": "integer", "minimum": 0},
                    "predicate": {"type": "string"},
                    "object_index": {"type": "integer", "minimum": 0},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {"type": "string"},
                },
            },
        },
    },
}


class OntologyGuidedLlmExtractor:
    """Use an LLM only to populate terms already declared in selected ontologies."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        prompt_version: str = "ontology-guided-v3",
        extractor_version: str = "1.2.0",
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._prompt_version = prompt_version
        self._extractor_version = extractor_version

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
    ) -> ClauseSemanticExtraction:
        vocabulary = FormalOntologyVocabulary.load(ontology_versions)
        context = clause.semantic_classification.model_dump(mode="json")
        projection = project_clause_content(clause.content)
        clause_reference = display_clause_reference(document_key, clause.reference)
        request = StructuredGenerationRequest(
            task="formal-semantic-knowledge-extraction",
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=0.0,
            output_schema=_SCHEMA,
            system_prompt=(
                "Extract engineering entities and relations from the clause. The allowed_classes "
                "and allowed_properties arrays are closed vocabularies: copy class_iri and "
                "predicate values exactly from those arrays and never invent, shorten, expand, "
                "or normalize a term. Omit an entity or relation if no allowed term fits. Do not "
                "infer cross-standard equivalence or mapping. Prefer the most specific allowed "
                "class and property entailed by the clause. EngineeringEntity and "
                "EngineeringConcept are last-resort fallback classes; use them only when no more "
                "specific allowed class fits. Prefer System, Subsystem, Element, "
                "HardwareComponent, SoftwareElement, Requirement, Specification, "
                "InterfaceSpecification, EngineeringQuantity, Metric, Parameter, Rate, "
                "TimeInterval, TechniqueOrMeasure, Fault, Error, Failure, SafetyMechanism, or "
                "SafetyState when applicable. Use containsClause only for document structure "
                "where a StandardsEntity contains a Clause; use hasPart/partOf for engineering "
                "composition. Use describes only as a final relation fallback when no more "
                "specific allowed property is entailed. Never materialize ontology class names "
                "or schema placeholders as source entities unless the clause itself explicitly "
                "refers to that concept. The entities array is ordered; relations MUST reference "
                "entities only by zero-based subject_index and object_index into that array. "
                "Evidence must be a short rationale, not a quotation from the source."
            ),
            user_prompt=json.dumps(
                {
                    "document_key": document_key,
                    "clause_reference": clause_reference,
                    "clause_title": clause.heading,
                    "clause_id": clause.id.value,
                    "clause_text": projection.text,
                    "semantic_context": context,
                    "allowed_classes": sorted(vocabulary.classes),
                    "allowed_properties": sorted(vocabulary.properties),
                },
                ensure_ascii=False,
            ),
            metadata={"ontology_versions": ontology_versions},
        )
        result = self._gateway.generate_structured(request)
        payload = dict(result.value)
        raw_entities = payload.get("entities", [])
        entity_resources_by_index: list[SemanticResource | None] = []
        entities_by_resource: dict[str, ExtractedEntity] = {}
        violations: list[ExtractionViolation] = []
        for raw in raw_entities:
            class_iri = str(raw["class_iri"]).strip()
            if class_iri not in vocabulary.classes:
                violations.append(
                    ExtractionViolation(
                        kind="undeclared_class",
                        term=class_iri,
                        reason="class is not declared by the selected formal ontologies",
                    )
                )
                entity_resources_by_index.append(None)
                continue
            label = str(raw["label"]).strip()
            resource = _entity_resource(
                document_key=document_key,
                clause_id=clause.id.value,
                label=label,
                class_iri=class_iri,
            )
            entities_by_resource.setdefault(
                resource.iri,
                ExtractedEntity(
                    id=resource,
                    class_iri=SemanticResource(iri=class_iri),
                    label=label,
                    confidence=float(raw["confidence"]),
                    evidence=str(raw["evidence"]),
                ),
            )
            entity_resources_by_index.append(resource)
        entities = list(entities_by_resource.values())
        relations = []
        for raw in payload.get("relations", []):
            predicate = str(raw["predicate"]).strip()
            subject_index = int(raw["subject_index"])
            object_index = int(raw["object_index"])
            if predicate not in vocabulary.properties:
                violations.append(
                    ExtractionViolation(
                        kind="undeclared_property",
                        term=predicate,
                        reason="property is not declared by the selected formal ontologies",
                    )
                )
                continue
            if not _valid_entity_index(subject_index, entity_resources_by_index) or not (
                _valid_entity_index(object_index, entity_resources_by_index)
            ):
                violations.append(
                    ExtractionViolation(
                        kind="invalid_relation",
                        term=predicate,
                        reason=(
                            "relation references an entity index that is out of range "
                            "or points to a rejected entity"
                        ),
                    )
                )
                continue
            subject = entity_resources_by_index[subject_index]
            object_ = entity_resources_by_index[object_index]
            assert subject is not None
            assert object_ is not None
            try:
                relation = ExtractedRelation(
                    subject_id=subject,
                    predicate=SemanticResource(iri=predicate),
                    object_id=object_,
                    confidence=float(raw["confidence"]),
                    evidence=str(raw["evidence"]),
                )
            except ValueError as error:
                violations.append(
                    ExtractionViolation(
                        kind="invalid_relation",
                        term=predicate,
                        reason=str(error),
                    )
                )
                continue
            relations.append(relation)
        return ClauseSemanticExtraction(
            clause_id=clause.id.value,
            clause_reference=clause_reference,
            clause_title=clause.heading,
            ontology_versions=ontology_versions,
            entities=tuple(entities),
            relations=tuple(relations),
            violations=tuple(violations),
            provenance=ExtractionProvenance(
                extractor="ontology-guided-llm",
                extractor_version=self._extractor_version,
                model=result.model,
                provider=result.provider,
                prompt_version=result.prompt_version,
                input_hash=result.input_hash,
                raw_response_hash=result.raw_response_hash,
                source_character_count=projection.source_character_count,
                semantic_input_character_count=projection.semantic_input_character_count,
                omitted_table_block_count=projection.omitted_table_block_count,
                omitted_table_character_count=projection.omitted_table_character_count,
            ),
        )


def _entity_resource(
    *, document_key: str, clause_id: str, label: str, class_iri: str
) -> SemanticResource:
    normalized_label = _normalize_entity_label(label)
    digest = hashlib.sha256(
        f"{document_key}|{clause_id}|{normalized_label}|{class_iri}".encode()
    ).hexdigest()[:20]
    return SemanticResource.stat(f"entity/{document_key}/{clause_id}/{digest}")


def _normalize_entity_label(label: str) -> str:
    normalized = unicodedata.normalize("NFKC", label).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _valid_entity_index(index: int, resources: list[SemanticResource | None]) -> bool:
    return 0 <= index < len(resources) and resources[index] is not None
