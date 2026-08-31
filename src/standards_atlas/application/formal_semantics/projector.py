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
    FormalAssertion,
    FormalSemanticProjection,
    SemanticBox,
    SemanticLiteral,
    SemanticRelationKind,
    SemanticResource,
)

PROJECTION_VERSION = "1.0.0"
CORE_ONTOLOGY_VERSION = "standards-atlas-core@1.2.0"
FUNCTIONAL_SAFETY_ONTOLOGY_VERSION = "functional-safety@1.2.0"
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

    def project(
        self,
        document: EngineeringDocument,
        *,
        knowledge_domains: tuple[str, ...] = (),
    ) -> FormalSemanticProjection:
        key = document.key.value
        document_resource = _document_resource(key)
        lineage_evidence = (document.lineage.artifact.id,) if document.lineage is not None else ()
        assertions: list[FormalAssertion] = []
        contexts: list[ContextFrame] = []

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

        ontology_versions = [CORE_ONTOLOGY_VERSION]
        if any(
            "functional-safety" in domain.lower()
            for domain in self._all_domains(document, explicit_domains)
        ):
            ontology_versions.append(FUNCTIONAL_SAFETY_ONTOLOGY_VERSION)

        return FormalSemanticProjection(
            source_document_key=key,
            projection_version=PROJECTION_VERSION,
            ontology_versions=tuple(ontology_versions),
            assertions=tuple(assertions),
            contexts=tuple(contexts),
        )

    def _all_domains(
        self,
        document: EngineeringDocument,
        explicit: tuple[str, ...],
    ) -> tuple[str, ...]:
        domains = list(explicit)
        for clause in document.clauses:
            domains.extend(
                item.knowledge_domain for item in clause.semantic_classification.domain_functions
            )
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
        semantic = clause.semantic_classification
        facets: list[ContextFacet] = []

        domains = list(explicit_domains)
        domains.extend(item.knowledge_domain for item in semantic.domain_functions)
        for domain in dict.fromkeys(domains):
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "inKnowledgeDomain",
                    _knowledge_domain_resource(domain),
                    "knowledge-domain",
                )
            )

        for value in semantic.statement_functions:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "statementFunction",
                    value.value,
                    "semantic-classification",
                )
            )
        for value in semantic.knowledge_kinds:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "knowledgeKind",
                    value.value,
                    "semantic-classification",
                )
            )
        for value in semantic.process_functions:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "processFunction",
                    value.value,
                    "semantic-classification",
                )
            )
        facets.append(
            _facet(
                ContextKind.SEMANTIC,
                "applicabilityPresent",
                semantic.applicability_present,
                "semantic-classification",
            )
        )
        for value in semantic.applicability_functions:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "applicabilityFunction",
                    value.value,
                    "semantic-classification",
                )
            )
        facets.append(
            _facet(
                ContextKind.SEMANTIC,
                "roleSemanticsPresent",
                semantic.role_semantics_present,
                "semantic-classification",
            )
        )
        for relation in semantic.role_relations:
            facets.append(
                _facet(
                    ContextKind.SEMANTIC,
                    "roleRelationClass",
                    relation.relation_class,
                    "semantic-classification",
                )
            )
        facets.append(
            _facet(
                ContextKind.SEMANTIC,
                "normativeStatus",
                clause.normative_status.value,
                "semantic-classification",
            )
        )
        for domain in semantic.domain_functions:
            facets.append(
                _facet(
                    ContextKind.EPISTEMIC,
                    "taxonomyVersion",
                    f"{domain.knowledge_domain}@{domain.taxonomy_version}",
                    "domain-function-taxonomy",
                )
            )
            for function in domain.functions:
                facets.append(
                    _facet(
                        ContextKind.SEMANTIC,
                        "domainFunction",
                        function,
                        f"knowledge-domain:{domain.knowledge_domain}",
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
