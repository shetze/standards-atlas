"""Deterministic Turtle serialization for provider-neutral semantic projections."""

from __future__ import annotations

import hashlib

from standards_atlas.domain.model import (
    FORMAL_SEMANTIC_NAMESPACE,
    ContextFacet,
    ContextFrame,
    ContextKind,
    FormalAssertion,
    FormalSemanticProjection,
    SemanticLiteral,
    SemanticResource,
)

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"


class TurtleFormalSemanticSerializer:
    """Serialize a projection as deterministic RDF/Turtle without owning graph semantics."""

    media_type = "text/turtle"

    def serialize(self, projection: FormalSemanticProjection) -> str:
        lines = [
            f"@prefix stat: <{FORMAL_SEMANTIC_NAMESPACE}> .",
            f"@prefix rdf: <{RDF}> .",
            f"@prefix xsd: <{XSD}> .",
            "",
        ]

        for assertion in projection.assertions:
            lines.extend(self._serialize_assertion(assertion))
        for context in projection.contexts:
            lines.extend(self._serialize_context(context))
        return "\n".join(lines).rstrip() + "\n"

    def _serialize_assertion(self, assertion: FormalAssertion) -> list[str]:
        subject = _iri(assertion.subject)
        predicate = _iri(assertion.predicate)
        object_ = _term(assertion.object)
        node = _iri(assertion.id)
        lines = [
            f"{subject} {predicate} {object_} .",
            f"{node} rdf:type stat:SemanticAssertion .",
            f"{node} stat:semanticBox {_literal(SemanticLiteral(value=assertion.box.value))} .",
            f"{node} stat:assertionSubject {subject} .",
            f"{node} stat:assertionPredicate {predicate} .",
            f"{node} stat:assertionObject {object_} .",
        ]
        lines.extend(
            f"{node} stat:qualifiedByContext {_iri(context_id)} ."
            for context_id in assertion.context_ids
        )
        lines.extend(
            f"{node} stat:evidenceId {_literal(SemanticLiteral(value=evidence_id))} ."
            for evidence_id in assertion.evidence_ids
        )
        lines.append("")
        return lines

    def _serialize_context(self, context: ContextFrame) -> list[str]:
        node = _iri(context.id)
        lines = [f"{node} rdf:type stat:ContextFrame ."]
        context_types = {facet.kind for facet in context.facets}
        type_names = {
            ContextKind.SEMANTIC: "SemanticContext",
            ContextKind.STRUCTURAL: "StructuralContext",
            ContextKind.EPISTEMIC: "EpistemicContext",
        }
        lines.extend(
            f"{node} rdf:type stat:{type_names[kind]} ."
            for kind in sorted(context_types, key=lambda item: item.value)
        )
        for facet in context.facets:
            lines.extend(self._serialize_facet(context, facet))
        lines.append("")
        return lines

    def _serialize_facet(self, context: ContextFrame, facet: ContextFacet) -> list[str]:
        context_node = _iri(context.id)
        facet_node = _iri(_facet_resource(context, facet))
        value = _term(facet.value)
        lines = [
            f"{context_node} {_iri(facet.predicate)} {value} .",
            f"{context_node} stat:hasContextFacet {facet_node} .",
            f"{facet_node} rdf:type stat:ContextFacet .",
            f"{facet_node} stat:contextKind {_literal(SemanticLiteral(value=facet.kind.value))} .",
            f"{facet_node} stat:facetPredicate {_iri(facet.predicate)} .",
        ]
        property_name = (
            "facetValue" if isinstance(facet.value, SemanticResource) else "facetLiteralValue"
        )
        lines.append(f"{facet_node} stat:{property_name} {value} .")
        lines.append(
            f"{facet_node} stat:facetSource {_literal(SemanticLiteral(value=facet.source))} ."
        )
        return lines


def _facet_resource(context: ContextFrame, facet: ContextFacet) -> SemanticResource:
    value = (
        facet.value.iri
        if isinstance(facet.value, SemanticResource)
        else repr((facet.value.value, facet.value.datatype_iri, facet.value.language))
    )
    raw = "|".join((context.id.iri, facet.kind.value, facet.predicate.iri, value, facet.source))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return SemanticResource.stat(f"context-facet/{digest}")


def _iri(resource: SemanticResource) -> str:
    return f"<{resource.iri}>"


def _term(value: SemanticResource | SemanticLiteral) -> str:
    return _iri(value) if isinstance(value, SemanticResource) else _literal(value)


def _literal(literal: SemanticLiteral) -> str:
    escaped = _escape(str(literal.value))
    if literal.language:
        return f'"{escaped}"@{literal.language}'
    if literal.datatype_iri:
        return f'"{escaped}"^^<{literal.datatype_iri}>'
    if isinstance(literal.value, bool):
        return f'"{str(literal.value).lower()}"^^xsd:boolean'
    if isinstance(literal.value, int):
        return f'"{literal.value}"^^xsd:integer'
    if isinstance(literal.value, float):
        return f'"{literal.value}"^^xsd:double'
    return f'"{escaped}"'


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
