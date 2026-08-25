from __future__ import annotations

from standards_atlas.adapters.rdf import TurtleFormalSemanticSerializer
from standards_atlas.application.formal_semantics import DeterministicFormalSemanticProjector
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def test_turtle_serializer_emits_direct_and_reified_assertions() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title='Example "Standard"',
        document_type=DocumentType.STANDARD,
        clauses=(
            Clause(
                id=ClauseId(value="1"),
                reference=StandardReference(standard="EXAMPLE", clause="1"),
                clause_type=ClauseType.CLAUSE,
            ),
        ),
    )
    projection = DeterministicFormalSemanticProjector().project(document)
    turtle = TurtleFormalSemanticSerializer().serialize(projection)

    assert "@prefix stat: <http://lunetix.org/standards-atlas#> ." in turtle
    assert "rdf:type stat:SemanticAssertion" in turtle
    assert "stat:qualifiedByContext" in turtle
    assert "stat:hasContextFacet" in turtle
    assert 'Example \\"Standard\\"' in turtle
    assert TurtleFormalSemanticSerializer.media_type == "text/turtle"
