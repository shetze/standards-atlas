from standards_atlas.adapters.atlasdata.semantic_tags import (
    decode_semantic_tags,
    encode_semantic_tags,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    KnowledgeKind,
    RoleRelationType,
    SemanticClassification,
    StatementFunction,
)


def test_semantic_tags_round_trip_versioned_taxonomy_codes() -> None:
    classification = SemanticClassification(
        statement_functions=(
            StatementFunction.REQUIREMENT,
            StatementFunction.PREREQUISITE,
        ),
        knowledge_kinds=(KnowledgeKind.TECHNIQUE_OR_MEASURE,),
        applicability_functions=(ApplicabilityFunction.EXCEPTION,),
        role_relation_types=(RoleRelationType.RESPONSIBLE_FOR,),
    )
    tags = encode_semantic_tags(classification, semantic_profile="functional-safety:1.0.0")
    assert tags == ("SP-REQ", "SS-PRE", "KK-TOM", "AF-XCP", "RR-RSP")
    decoded = decode_semantic_tags(tags, semantic_profile="functional-safety:1.0.0")
    assert decoded["primary_statement_function"] == ("requirement",)
    assert decoded["secondary_statement_functions"] == ("prerequisite",)
    assert decoded["knowledge_kinds"] == ("technique_or_measure",)
