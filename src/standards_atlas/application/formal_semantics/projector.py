"""Deterministic ABox/CBox projection from canonical engineering documents."""

from __future__ import annotations

import hashlib
from urllib.parse import quote

from standards_atlas.domain.model import (
    ContextFacet,
    ContextFrame,
    ContextKind,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    FormalAssertion,
    FormalSemanticProjection,
    KnowledgeEntity,
    LiteralAssertionObject,
    NormativeAssertion,
    SemanticBox,
    SemanticLiteral,
    SemanticRelationKind,
    SemanticResource,
)

from .knowledge_validation import DocumentKnowledgeOntologyValidator
from .resource_repository import ResourceFormalOntologyRepository

PROJECTION_VERSION = "1.0.0"
CORE_ONTOLOGY_VERSION = "standards-atlas-core@2.0.0"
FUNCTIONAL_SAFETY_ONTOLOGY_VERSION = "functional-safety@2.1.0"
RDF_TYPE = SemanticResource(iri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

_RELATION_PREDICATES: dict[SemanticRelationKind, str] = {
    SemanticRelationKind.REFERENCES: "references",
    SemanticRelationKind.NORMATIVE_REFERENCE: "normativeReferences",
    SemanticRelationKind.INFORMATIVE_REFERENCE: "informativeReferences",
    SemanticRelationKind.REFINES: "refines",
    SemanticRelationKind.IMPLEMENTS: "implements",
    SemanticRelationKind.VERIFIES: "verifies",
    SemanticRelationKind.VALIDATES: "validates",
    SemanticRelationKind.DEPENDS_ON: "dependsOn",
    SemanticRelationKind.CONFLICTS_WITH: "conflictsWith",
    SemanticRelationKind.EQUIVALENT_TO: "equivalentTo",
    SemanticRelationKind.DERIVED_FROM: "derivedFrom",
    SemanticRelationKind.APPLIES_TO: "appliesTo",
    SemanticRelationKind.PROVIDES_EVIDENCE_FOR: "providesEvidenceFor",
}


def _segment(value: str) -> str:
    return quote(value.strip(), safe="-._~")


def _document_resource(document_key: str) -> SemanticResource:
    return SemanticResource.stat(f"document/{_segment(document_key)}")


def _clause_resource(document_key: str, clause_id: str) -> SemanticResource:
    return SemanticResource.stat(f"document/{_segment(document_key)}/clause/{_segment(clause_id)}")


def _knowledge_domain_resource(value: str) -> SemanticResource:
    return SemanticResource.stat(f"knowledge-domain/{_segment(value)}")


def _knowledge_entity_resource(document_key: str, entity_id: str) -> SemanticResource:
    return SemanticResource.stat(
        f"document/{_segment(document_key)}/knowledge/entity/{_segment(entity_id)}"
    )


def _knowledge_assertion_context_resource(
    document_key: str,
    assertion_id: str,
) -> SemanticResource:
    return SemanticResource.stat(
        f"context/{_segment(document_key)}/knowledge/assertion/{_segment(assertion_id)}"
    )


def _context_resource(document_key: str, clause_id: str) -> SemanticResource:
    return SemanticResource.stat(f"context/{_segment(document_key)}/{_segment(clause_id)}")


def _target_resource(
    document_key: str,
    target_document: str | None,
    target_clause: str | None,
    reference: str,
) -> SemanticResource:
    if target_clause:
        return _clause_resource(target_document or document_key, target_clause)
    target_key = target_document or document_key
    return SemanticResource.stat(f"document/{_segment(target_key)}/reference/{_segment(reference)}")


def _assertion_id(
    box: SemanticBox,
    subject: SemanticResource,
    predicate: SemanticResource,
    object_: SemanticResource | SemanticLiteral,
    context_ids: tuple[SemanticResource, ...],
) -> SemanticResource:
    object_key = (
        object_.iri
        if isinstance(object_, SemanticResource)
        else repr((object_.value, object_.datatype_iri, object_.language))
    )
    raw = "|".join(
        [
            box.value,
            subject.iri,
            predicate.iri,
            object_key,
            *(item.iri for item in context_ids),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return SemanticResource.stat(f"assertion/{digest}")


def _assertion(
    box: SemanticBox,
    subject: SemanticResource,
    predicate: SemanticResource,
    object_: SemanticResource | SemanticLiteral,
    *,
    contexts: tuple[SemanticResource, ...] = (),
    evidence_ids: tuple[str, ...] = (),
) -> FormalAssertion:
    return FormalAssertion(
        id=_assertion_id(box, subject, predicate, object_, contexts),
        box=box,
        subject=subject,
        predicate=predicate,
        object=object_,
        context_ids=contexts,
        evidence_ids=evidence_ids,
    )


def _literal(value: object) -> SemanticLiteral:
    return SemanticLiteral(value=value)


def _facet(
    kind: ContextKind,
    predicate: str,
    value: object | SemanticResource,
    source: str,
) -> ContextFacet:
    return ContextFacet(
        kind=kind,
        predicate=SemanticResource.stat(predicate),
        value=value if isinstance(value, SemanticResource) else _literal(value),
        source=source,
    )


class DeterministicFormalSemanticProjector:
    """Project only already-known document facts; never infer new engineering entities."""

    def __init__(
        self,
        ontology_repository: ResourceFormalOntologyRepository | None = None,
    ) -> None:
        self._knowledge_validator = DocumentKnowledgeOntologyValidator(ontology_repository)

    def project(
        self,
        document: EngineeringDocument,
        *,
        knowledge_domains: tuple[str, ...] = (),
    ) -> FormalSemanticProjection:
        self._knowledge_validator.validate(document.knowledge)

        key = document.key.value
        document_resource = _document_resource(key)
        lineage_evidence = (document.lineage.artifact.id,) if document.lineage is not None else ()
        assertions: list[FormalAssertion] = []
        contexts: list[ContextFrame] = []
        clause_contexts: dict[str, ContextFrame] = {}

        document_class = (
            "Standard" if document.document_type is DocumentType.STANDARD else "EngineeringDocument"
        )
        assertions.append(
            _assertion(
                SemanticBox.ABOX,
                document_resource,
                RDF_TYPE,
                SemanticResource.stat(document_class),
                evidence_ids=lineage_evidence,
            )
        )
        for predicate, value in (
            ("documentKey", key),
            ("title", document.title),
            ("documentType", document.document_type.value),
        ):
            assertions.append(
                _assertion(
                    SemanticBox.ABOX,
                    document_resource,
                    SemanticResource.stat(predicate),
                    _literal(value),
                    evidence_ids=lineage_evidence,
                )
            )
        if document.year is not None:
            assertions.append(
                _assertion(
                    SemanticBox.ABOX,
                    document_resource,
                    SemanticResource.stat("publicationYear"),
                    _literal(document.year),
                    evidence_ids=lineage_evidence,
                )
            )
        if document.version:
            assertions.append(
                _assertion(
                    SemanticBox.ABOX,
                    document_resource,
                    SemanticResource.stat("documentVersion"),
                    _literal(document.version),
                    evidence_ids=lineage_evidence,
                )
            )

        explicit_domains = tuple(
            dict.fromkeys(domain.strip() for domain in knowledge_domains if domain.strip())
        )
        known_clause_ids = {clause.id.value for clause in document.clauses}

        for clause in document.clauses:
            clause_resource = _clause_resource(key, clause.id.value)
            context = self._context_for_clause(
                document,
                clause.id.value,
                explicit_domains,
            )
            contexts.append(context)
            clause_contexts[clause.id.value] = context
            context_ids = (context.id,)

            assertions.extend(
                (
                    _assertion(
                        SemanticBox.ABOX,
                        document_resource,
                        SemanticResource.stat("containsClause"),
                        clause_resource,
                        evidence_ids=lineage_evidence,
                    ),
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        RDF_TYPE,
                        SemanticResource.stat("Clause"),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    ),
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat("referenceText"),
                        _literal(clause.reference.as_text()),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    ),
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat("clauseType"),
                        _literal(clause.clause_type.value),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    ),
                )
            )
            if clause.heading:
                assertions.append(
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat("title"),
                        _literal(clause.heading),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    )
                )
            if clause.parent_id is not None and clause.parent_id.value in known_clause_ids:
                assertions.append(
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat("hasParentClause"),
                        _clause_resource(key, clause.parent_id.value),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    )
                )
            sibling = clause.structural_context.sibling if clause.structural_context else None
            if sibling and sibling.next_clause_id and sibling.next_clause_id in known_clause_ids:
                assertions.append(
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat("precedesClause"),
                        _clause_resource(key, sibling.next_clause_id),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    )
                )

            for relation in clause.reference_relations:
                assertions.append(
                    _assertion(
                        SemanticBox.ABOX,
                        clause_resource,
                        SemanticResource.stat(_RELATION_PREDICATES[relation.kind]),
                        _target_resource(
                            key,
                            relation.target_document_key,
                            relation.target_clause_id,
                            relation.target_reference,
                        ),
                        contexts=context_ids,
                        evidence_ids=lineage_evidence,
                    )
                )

        knowledge_assertions, knowledge_contexts = self._project_document_knowledge(
            document,
            clause_contexts=clause_contexts,
        )
        assertions.extend(knowledge_assertions)
        contexts.extend(knowledge_contexts)

        ontology_versions = [CORE_ONTOLOGY_VERSION]
        if any(
            "functional-safety" in domain.lower()
            for domain in self._all_domains(document, explicit_domains)
        ):
            ontology_versions.append(FUNCTIONAL_SAFETY_ONTOLOGY_VERSION)
        ontology_versions.extend(document.knowledge.ontology_versions)
        ontology_versions = list(dict.fromkeys(ontology_versions))

        return FormalSemanticProjection(
            source_document_key=key,
            projection_version=PROJECTION_VERSION,
            ontology_versions=tuple(ontology_versions),
            assertions=tuple(assertions),
            contexts=tuple(contexts),
        )

    def _project_document_knowledge(
        self,
        document: EngineeringDocument,
        *,
        clause_contexts: dict[str, ContextFrame],
    ) -> tuple[list[FormalAssertion], list[ContextFrame]]:
        knowledge = document.knowledge
        if not knowledge.entities and not knowledge.assertions:
            return [], []

        anchor_by_id = {anchor.id: anchor for anchor in knowledge.evidence_anchors}
        entity_resources = {
            entity.id: _knowledge_entity_resource(document.key.value, entity.id)
            for entity in knowledge.entities
        }
        assertions: list[FormalAssertion] = []
        contexts: list[ContextFrame] = []

        for entity in knowledge.entities:
            context_ids = self._entity_context_ids(entity, anchor_by_id, clause_contexts)
            assertions.append(
                _assertion(
                    SemanticBox.ABOX,
                    entity_resources[entity.id],
                    RDF_TYPE,
                    SemanticResource(iri=entity.class_iri),
                    contexts=context_ids,
                    evidence_ids=entity.source_anchor_ids,
                )
            )

        for assertion in knowledge.assertions:
            knowledge_context = self._knowledge_context_for_assertion(document, assertion)
            contexts.append(knowledge_context)
            source_context = clause_contexts[assertion.source_clause_id.value]
            assertions.append(
                _assertion(
                    SemanticBox.ABOX,
                    entity_resources[assertion.subject_id],
                    SemanticResource(iri=assertion.predicate),
                    self._assertion_object(assertion, entity_resources),
                    contexts=(source_context.id, knowledge_context.id),
                    evidence_ids=assertion.evidence_anchor_ids,
                )
            )

        return assertions, contexts

    @staticmethod
    def _entity_context_ids(
        entity: KnowledgeEntity,
        anchor_by_id: dict[str, EvidenceAnchor],
        clause_contexts: dict[str, ContextFrame],
    ) -> tuple[SemanticResource, ...]:
        ids: list[SemanticResource] = []
        seen: set[str] = set()
        for anchor_id in entity.source_anchor_ids:
            anchor = anchor_by_id[anchor_id]
            clause_id = anchor.clause_id.value
            context_id = clause_contexts[clause_id].id
            if context_id.iri not in seen:
                seen.add(context_id.iri)
                ids.append(context_id)
        return tuple(ids)

    @staticmethod
    def _assertion_object(
        assertion: NormativeAssertion,
        entity_resources: dict[str, SemanticResource],
    ) -> SemanticResource | SemanticLiteral:
        if isinstance(assertion.object, EntityAssertionObject):
            return entity_resources[assertion.object.entity_id]
        if not isinstance(assertion.object, LiteralAssertionObject):
            raise TypeError(f"unsupported normative assertion object: {type(assertion.object)!r}")
        return SemanticLiteral(
            value=assertion.object.value,
            datatype_iri=assertion.object.datatype_iri,
            language=assertion.object.language,
        )

    @staticmethod
    def _knowledge_context_for_assertion(
        document: EngineeringDocument,
        assertion: NormativeAssertion,
    ) -> ContextFrame:
        provenance = assertion.provenance
        facets = [
            _facet(
                ContextKind.SEMANTIC,
                "normativeForce",
                assertion.normative_force.value,
                "document-knowledge",
            ),
            _facet(
                ContextKind.EPISTEMIC,
                "knowledgeDerivationMethod",
                provenance.method.value,
                "document-knowledge",
            ),
            _facet(
                ContextKind.EPISTEMIC,
                "knowledgeProducer",
                provenance.producer,
                "document-knowledge",
            ),
        ]
        for predicate, value in (
            ("knowledgeProducerVersion", provenance.producer_version),
            ("qualificationReference", provenance.qualification_reference),
            ("reviewReference", provenance.review_reference),
            ("knowledgeInputHash", provenance.input_hash),
        ):
            if value:
                facets.append(
                    _facet(
                        ContextKind.EPISTEMIC,
                        predicate,
                        value,
                        "document-knowledge",
                    )
                )
        return ContextFrame(
            id=_knowledge_assertion_context_resource(document.key.value, assertion.id),
            facets=tuple(facets),
        )

    def _all_domains(
        self,
        document: EngineeringDocument,
        explicit: tuple[str, ...],
    ) -> tuple[str, ...]:
        domains = list(explicit)
        for clause in document.clauses:
            if clause.structural_profile:
                domains.extend(
                    item.taxonomy for item in clause.structural_profile.domain_categories
                )
        return tuple(dict.fromkeys(domains))

    def _context_for_clause(
        self,
        document: EngineeringDocument,
        clause_id: str,
        explicit_domains: tuple[str, ...],
    ) -> ContextFrame:
        clause = next(item for item in document.clauses if item.id.value == clause_id)
        facets: list[ContextFacet] = [
            _facet(
                ContextKind.STRUCTURAL,
                "sourceClause",
                _clause_resource(document.key.value, clause_id),
                "formal-semantic-projector",
            )
        ]

        domains = list(explicit_domains)
        for domain in dict.fromkeys(domains):
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "inKnowledgeDomain",
                    _knowledge_domain_resource(domain),
                    "knowledge-domain",
                )
            )

        applicability = clause.applicability
        facets.append(
            _facet(
                ContextKind.SEMANTIC,
                "applicabilityPresent",
                applicability.present,
                "applicability",
            )
        )
        if applicability.polarity is not None:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "applicabilityPolarity",
                    applicability.polarity.value,
                    "applicability",
                )
            )

        primary_subject = clause.primary_subject
        if primary_subject is not None:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "primarySubject",
                    primary_subject.normalized_label,
                    "subject-identification",
                )
            )
            facets.append(
                _facet(
                    ContextKind.EPISTEMIC,
                    "subjectConfidence",
                    primary_subject.confidence,
                    "subject-identification",
                )
            )
            facets.append(
                _facet(
                    ContextKind.EPISTEMIC,
                    "subjectEvidenceKind",
                    primary_subject.evidence.kind,
                    "subject-identification",
                )
            )

        if clause.document_structure:
            structure = clause.document_structure
            facets.append(
                _facet(
                    ContextKind.STRUCTURAL,
                    "documentCategory",
                    structure.category.value,
                    f"document-family:{structure.family}",
                )
            )

        profile = clause.structural_profile
        if profile:
            if profile.canonical_section:
                facets.append(
                    _facet(
                        ContextKind.STRUCTURAL,
                        "canonicalSection",
                        profile.canonical_section.value,
                        "structural-profile",
                    )
                )
            if profile.annex_status:
                facets.append(
                    _facet(
                        ContextKind.STRUCTURAL,
                        "annexStatus",
                        profile.annex_status.value,
                        "structural-profile",
                    )
                )
            for category in profile.document_categories:
                facets.append(
                    _facet(
                        ContextKind.STRUCTURAL,
                        "documentCategory",
                        f"{category.taxonomy}:{category.category}",
                        "structural-profile",
                    )
                )
                if category.version:
                    facets.append(
                        _facet(
                            ContextKind.EPISTEMIC,
                            "taxonomyVersion",
                            f"{category.taxonomy}@{category.version}",
                            "structural-profile",
                        )
                    )
            for category in profile.domain_categories:
                facets.append(
                    _facet(
                        ContextKind.SEMANTIC,
                        "domainCategory",
                        f"{category.taxonomy}:{category.category}",
                        "structural-profile",
                    )
                )
                if category.version:
                    facets.append(
                        _facet(
                            ContextKind.EPISTEMIC,
                            "taxonomyVersion",
                            f"{category.taxonomy}@{category.version}",
                            "structural-profile",
                        )
                    )

        structural = clause.structural_context
        if structural:
            facets.append(
                _facet(
                    ContextKind.STRUCTURAL,
                    "nodeKind",
                    structural.node_kind.value,
                    "structural-context",
                )
            )
            if structural.sibling:
                facets.append(
                    _facet(
                        ContextKind.STRUCTURAL,
                        "siblingIndex",
                        structural.sibling.index,
                        "structural-context",
                    )
                )
                facets.append(
                    _facet(
                        ContextKind.STRUCTURAL,
                        "siblingCount",
                        structural.sibling.count,
                        "structural-context",
                    )
                )

        facets.append(
            _facet(
                ContextKind.EPISTEMIC,
                "projectionRuleVersion",
                PROJECTION_VERSION,
                "formal-semantic-projector",
            )
        )
        if document.lineage is not None:
            facets.append(
                _facet(
                    ContextKind.EPISTEMIC,
                    "sourceArtifactId",
                    document.lineage.artifact.id,
                    "artifact-lineage",
                )
            )
            facets.append(
                _facet(
                    ContextKind.EPISTEMIC,
                    "sourceArtifactHash",
                    document.lineage.artifact.content_hash,
                    "artifact-lineage",
                )
            )

        unique: list[ContextFacet] = []
        seen: set[tuple[str, str, str]] = set()
        for facet in facets:
            value_key = (
                facet.value.iri
                if isinstance(facet.value, SemanticResource)
                else repr(
                    (
                        facet.value.value,
                        facet.value.datatype_iri,
                        facet.value.language,
                    )
                )
            )
            key = (facet.kind.value, facet.predicate.iri, value_key)
            if key not in seen:
                seen.add(key)
                unique.append(facet)
        return ContextFrame(
            id=_context_resource(document.key.value, clause_id),
            facets=tuple(unique),
        )
