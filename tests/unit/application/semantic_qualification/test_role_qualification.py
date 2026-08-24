from standards_atlas.application.semantic_qualification.role_qualification import (
    detect_role_candidate,
    field_match_metrics,
    relation_tuple_consensus,
    tuple_set_similarity,
)
from standards_atlas.domain.model import RoleRelation, RoleRelationType


def relation(actor: str, kind: RoleRelationType, target: str) -> RoleRelation:
    return RoleRelation(actor=actor, relation=kind, target=target)


def test_candidate_marker_detects_passive_role_semantics() -> None:
    result = detect_role_candidate("The analysis shall be verified independently.")
    assert result.candidate is True
    assert "verification" in result.markers
    assert "independence" in result.markers


def test_candidate_marker_is_not_a_classifier() -> None:
    result = detect_role_candidate("The supplier identifier is stored in the record.")
    assert result.candidate is True
    assert result.markers == ("supplier",)


def test_tuple_consensus_requires_complete_tuple_agreement() -> None:
    votes = {
        "m1": (relation("Verifier", RoleRelationType.VERIFIES, "analysis"),),
        "m2": (relation("verifier", RoleRelationType.VERIFIES, "Analysis"),),
        "m3": (relation("Validator", RoleRelationType.VALIDATES, "analysis"),),
    }
    result = relation_tuple_consensus(votes, minimum_support=0.6)
    assert len(result) == 1
    assert result[0].actor == "verifier"
    assert result[0].relation_class == "performance"
    assert result[0].target == "analysis"
    assert result[0].support == 2 / 3


def test_tuple_set_similarity_scores_complete_relations() -> None:
    expected = (relation("Verifier", RoleRelationType.VERIFIES, "analysis"),)
    actual = (
        relation("Verifier", RoleRelationType.VERIFIES, "analysis"),
        relation("Validator", RoleRelationType.VALIDATES, "system"),
    )
    metrics = tuple_set_similarity(expected, actual)
    assert metrics == {"precision": 0.5, "recall": 1.0, "f1": 2 / 3}


def test_field_metrics_explain_partial_tuple_mismatch() -> None:
    expected = relation("Verifier", RoleRelationType.VERIFIES, "analysis")
    actual = relation("Verifier", RoleRelationType.VERIFIES, "report")
    metrics = field_match_metrics(expected, actual)
    assert metrics == {
        "actor_match": True,
        "relation_class_match": True,
        "target_match": False,
    }
