"""Structured LLM adapter for ontology-guided concept and relation extraction."""

from __future__ import annotations

import hashlib
import json

from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest
from standards_atlas.application.semantic_extraction import FormalOntologyVocabulary
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
                "required": ["id", "class_iri", "label", "confidence", "evidence"],
                "properties": {
                    "id": {"type": "string"},
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
                "required": ["subject_id", "predicate", "object_id", "confidence", "evidence"],
                "properties": {
                    "subject_id": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object_id": {"type": "string"},
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
        prompt_version: str = "ontology-guided-v1",
        extractor_version: str = "1.0.0",
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
                "infer cross-standard equivalence or mapping. Evidence must be a short rationale, "
                "not a quotation from the source."
            ),
            user_prompt=json.dumps(
                {
                    "document_key": document_key,
                    "clause_id": clause.id.value,
                    "clause_text": clause.plain_text,
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
        entity_ids: dict[str, SemanticResource] = {}
        entities = []
        violations: list[ExtractionViolation] = []
        for raw in raw_entities:
            local_id = str(raw["id"]).strip()
            class_iri = str(raw["class_iri"]).strip()
            if class_iri not in vocabulary.classes:
                violations.append(
                    ExtractionViolation(
                        kind="undeclared_class",
                        term=class_iri,
                        reason="class is not declared by the selected formal ontologies",
                    )
                )
                continue
            digest = hashlib.sha256(
                f"{document_key}|{clause.id.value}|{local_id}|{class_iri}".encode()
            ).hexdigest()[:20]
            resource = SemanticResource.stat(f"entity/{document_key}/{clause.id.value}/{digest}")
            entity_ids[local_id] = resource
            entities.append(
                ExtractedEntity(
                    id=resource,
                    class_iri=SemanticResource(iri=class_iri),
                    label=str(raw["label"]),
                    confidence=float(raw["confidence"]),
                    evidence=str(raw["evidence"]),
                )
            )
        relations = []
        for raw in payload.get("relations", []):
            predicate = str(raw["predicate"]).strip()
            subject_id = str(raw["subject_id"]).strip()
            object_id = str(raw["object_id"]).strip()
            if predicate not in vocabulary.properties:
                violations.append(
                    ExtractionViolation(
                        kind="undeclared_property",
                        term=predicate,
                        reason="property is not declared by the selected formal ontologies",
                    )
                )
                continue
            if subject_id not in entity_ids or object_id not in entity_ids:
                violations.append(
                    ExtractionViolation(
                        kind="invalid_relation",
                        term=predicate,
                        reason="relation references an entity rejected or missing in the response",
                    )
                )
                continue
            try:
                relation = ExtractedRelation(
                    subject_id=entity_ids[subject_id],
                    predicate=SemanticResource(iri=predicate),
                    object_id=entity_ids[object_id],
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
            ),
        )
