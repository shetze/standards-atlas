"""Project extracted ontology-grounded knowledge into an existing ABox/CBox projection."""

from __future__ import annotations

import hashlib

from standards_atlas.domain.model import (
    ContextFacet,
    ContextFrame,
    ContextKind,
    DocumentSemanticExtraction,
    FormalAssertion,
    FormalSemanticProjection,
    SemanticBox,
    SemanticLiteral,
    SemanticResource,
)

RDF_TYPE = SemanticResource(iri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def _resource(local: str) -> SemanticResource:
    return SemanticResource.stat(local)


def _assertion(
    subject: SemanticResource,
    predicate: SemanticResource,
    object_: SemanticResource | SemanticLiteral,
    *,
    context: SemanticResource,
    evidence: str,
) -> FormalAssertion:
    object_key = object_.iri if isinstance(object_, SemanticResource) else repr(object_.value)
    raw = "|".join((subject.iri, predicate.iri, object_key, context.iri, evidence))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return FormalAssertion(
        id=_resource(f"assertion/{digest}"),
        box=SemanticBox.ABOX,
        subject=subject,
        predicate=predicate,
        object=object_,
        context_ids=(context,),
        evidence_ids=(evidence,),
    )


def _epistemic_context(
    *,
    document_key: str,
    clause_id: str,
    item_key: str,
    confidence: float,
    rationale: str,
    extractor: str,
    extractor_version: str,
    model: str | None,
    provider: str | None,
    prompt_version: str | None,
    input_hash: str | None,
    raw_response_hash: str | None,
) -> ContextFrame:
    digest = hashlib.sha256(item_key.encode("utf-8")).hexdigest()[:16]
    facets = [
        ContextFacet(
            kind=ContextKind.EPISTEMIC,
            predicate=_resource("confidence"),
            value=SemanticLiteral(value=confidence),
            source="semantic-extraction",
        ),
        ContextFacet(
            kind=ContextKind.EPISTEMIC,
            predicate=_resource("extractionRationale"),
            value=SemanticLiteral(value=rationale),
            source="semantic-extraction",
        ),
        ContextFacet(
            kind=ContextKind.EPISTEMIC,
            predicate=_resource("extractor"),
            value=SemanticLiteral(value=extractor),
            source="semantic-extraction",
        ),
        ContextFacet(
            kind=ContextKind.EPISTEMIC,
            predicate=_resource("extractorVersion"),
            value=SemanticLiteral(value=extractor_version),
            source="semantic-extraction",
        ),
    ]
    for predicate, value in (
        ("modelIdentifier", model),
        ("providerIdentifier", provider),
        ("promptVersion", prompt_version),
        ("inputHash", input_hash),
        ("rawResponseHash", raw_response_hash),
    ):
        if value:
            facets.append(
                ContextFacet(
                    kind=ContextKind.EPISTEMIC,
                    predicate=_resource(predicate),
                    value=SemanticLiteral(value=value),
                    source="semantic-extraction",
                )
            )
    return ContextFrame(
        id=_resource(f"context/extraction/{document_key}/{clause_id}/{digest}"),
        facets=tuple(facets),
    )


class SemanticExtractionProjectionAugmenter:
    """Add extracted knowledge without changing the canonical EngineeringDocument."""

    def augment(
        self,
        projection: FormalSemanticProjection,
        extraction: DocumentSemanticExtraction,
    ) -> FormalSemanticProjection:
        if projection.source_document_key != extraction.source_document_key:
            raise ValueError("projection and extraction must refer to the same document")

        assertions = list(projection.assertions)
        contexts = list(projection.contexts)
        for clause in extraction.clauses:
            clause_resource = _resource(
                f"document/{projection.source_document_key}/clause/{clause.clause_id}"
            )
            provenance = clause.provenance
            for entity in clause.entities:
                context = _epistemic_context(
                    document_key=projection.source_document_key,
                    clause_id=clause.clause_id,
                    item_key=f"entity|{entity.id.iri}|{entity.class_iri.iri}",
                    confidence=entity.confidence,
                    rationale=entity.evidence,
                    extractor=provenance.extractor,
                    extractor_version=provenance.extractor_version,
                    model=provenance.model,
                    provider=provenance.provider,
                    prompt_version=provenance.prompt_version,
                    input_hash=provenance.input_hash,
                    raw_response_hash=provenance.raw_response_hash,
                )
                contexts.append(context)
                evidence_id = f"semantic-extraction:{clause.clause_id}:{entity.id.iri}"
                assertions.append(
                    _assertion(
                        entity.id,
                        RDF_TYPE,
                        entity.class_iri,
                        context=context.id,
                        evidence=evidence_id,
                    )
                )
                assertions.append(
                    _assertion(
                        clause_resource,
                        _resource("describes"),
                        entity.id,
                        context=context.id,
                        evidence=evidence_id,
                    )
                )
            for index, relation in enumerate(clause.relations):
                context = _epistemic_context(
                    document_key=projection.source_document_key,
                    clause_id=clause.clause_id,
                    item_key=(
                        f"relation|{relation.subject_id.iri}|{relation.predicate.iri}|"
                        f"{relation.object_id.iri}|{index}"
                    ),
                    confidence=relation.confidence,
                    rationale=relation.evidence,
                    extractor=provenance.extractor,
                    extractor_version=provenance.extractor_version,
                    model=provenance.model,
                    provider=provenance.provider,
                    prompt_version=provenance.prompt_version,
                    input_hash=provenance.input_hash,
                    raw_response_hash=provenance.raw_response_hash,
                )
                contexts.append(context)
                assertions.append(
                    _assertion(
                        relation.subject_id,
                        relation.predicate,
                        relation.object_id,
                        context=context.id,
                        evidence=f"semantic-extraction:{clause.clause_id}:relation:{index}",
                    )
                )

        ontology_versions = tuple(
            dict.fromkeys(
                (
                    *projection.ontology_versions,
                    *(
                        version
                        for clause in extraction.clauses
                        for version in clause.ontology_versions
                    ),
                )
            )
        )
        return projection.model_copy(
            update={
                "ontology_versions": ontology_versions,
                "assertions": tuple(assertions),
                "contexts": tuple(contexts),
            }
        )
