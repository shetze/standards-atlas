import pytest
from pydantic import ValidationError

from standards_atlas.domain.model.identifiers import ClauseId, DocumentKey
from standards_atlas.domain.model.relation import Relation, RelationScope, RelationType


def test_external_relation_identifies_target_document() -> None:
    relation = Relation(
        source_id=ClauseId(value="clause-source"),
        target_id=ClauseId(value="clause-target"),
        target_document_key=DocumentKey(value="IEC61508-3"),
        relation_type=RelationType.REFERENCES,
        scope=RelationScope.EXTERNAL,
    )

    assert relation.scope == RelationScope.EXTERNAL


def test_external_relation_requires_target_document() -> None:
    with pytest.raises(ValidationError, match="target_document_key"):
        Relation(
            source_id=ClauseId(value="clause-source"),
            target_id=ClauseId(value="clause-target"),
            relation_type=RelationType.REFERENCES,
            scope=RelationScope.EXTERNAL,
        )
