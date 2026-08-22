"""Role-semantics qualification helpers.

Presence and structured relation extraction are evaluated independently.  The
helpers in this module are intentionally side-effect free so they can be reused
by matrix consensus, focused role corpora, and HITL tooling.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import RoleRelation, RoleRelationType

_ROLE_CANDIDATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("role", r"\brole\b"),
        ("responsibility", r"\bresponsib(?:le|ility|ilities)\b"),
        ("verification", r"\bverif(?:y|ies|ied|ication|ier|iers)\b"),
        ("validation", r"\bvalidat(?:e|es|ed|ion|or|ors)\b"),
        ("approval", r"\bapprov(?:e|es|ed|al|als)\b"),
        ("assessment", r"\bassess(?:or|ors|ment|ments)\b"),
        ("supplier", r"\bsupplier(?:s)?\b"),
        ("manufacturer", r"\bmanufacturer(?:s)?\b"),
        ("developer", r"\bdeveloper(?:s)?\b"),
        ("authority", r"\bauthorit(?:y|ies)\b"),
        ("committee", r"\bcommittee(?:s)?\b"),
        ("independence", r"\bindependen(?:t|ce|tly)\b"),
        ("assignment", r"\bassign(?:ed|ment|ments)?\b"),
        ("participation", r"\bparticipat(?:e|es|ed|ion)\b"),
        ("consultation", r"\bconsult(?:ed|s|ation)?\b"),
        ("information", r"\binform(?:ed|s|ation)?\b"),
        ("shall_ensure", r"\bshall\s+ensure\b"),
        ("shall_perform", r"\bshall\s+(?:be\s+)?perform(?:ed)?\b"),
    )
)


class RoleCandidateEvidence(BaseModel):
    """Deterministic signal that a clause deserves role-focused attention."""

    model_config = ConfigDict(frozen=True)

    candidate: bool = False
    markers: tuple[str, ...] = ()


class NormalizedRoleRelation(BaseModel):
    """Comparison-friendly representation of one extracted role relation."""

    model_config = ConfigDict(frozen=True)

    actor: str
    relation: RoleRelationType
    target: str
    condition: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str | None]:
        return (self.actor, self.relation.value, self.target, self.condition)


class RoleTupleConsensus(BaseModel):
    """Cross-model support for one normalized actor-relation-target tuple."""

    model_config = ConfigDict(frozen=True)

    actor: str
    relation: RoleRelationType
    target: str
    condition: str | None = None
    support: float = Field(ge=0.0, le=1.0)
    supporting_models: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


class RoleQualificationMetrics(BaseModel):
    """Metrics for role-semantics presence and tuple-set extraction."""

    model_config = ConfigDict(frozen=True)

    clause_count: int = Field(ge=0)
    candidate_clause_count: int = Field(ge=0)
    positive_presence_clause_count: int = Field(ge=0)
    candidate_consensus_negative_count: int = Field(ge=0)
    extracted_tuple_count: int = Field(ge=0)
    tuple_consensus_count: int = Field(ge=0)


def detect_role_candidate(text: str | None) -> RoleCandidateEvidence:
    """Return deterministic lexical evidence without making a semantic decision."""
    value = text or ""
    markers = tuple(name for name, pattern in _ROLE_CANDIDATE_PATTERNS if pattern.search(value))
    return RoleCandidateEvidence(candidate=bool(markers), markers=markers)


def normalize_relation(relation: RoleRelation) -> NormalizedRoleRelation:
    """Normalize actor/target text for stable cross-model tuple matching."""
    return NormalizedRoleRelation(
        actor=_normalize_text(relation.actor),
        relation=relation.relation,
        target=_normalize_text(relation.target),
        condition=_normalize_text(relation.condition) if relation.condition else None,
    )


def relation_tuple_consensus(
    model_relations: dict[str, Iterable[RoleRelation]],
    *,
    minimum_support: float = 0.6,
) -> tuple[RoleTupleConsensus, ...]:
    """Build tuple-set consensus instead of collapsing relations to one primary label."""
    if not model_relations:
        return ()
    total_models = len(model_relations)
    voters: dict[tuple[str, str, str, str | None], set[str]] = {}
    exemplars: dict[tuple[str, str, str, str | None], RoleRelation] = {}
    evidence: dict[tuple[str, str, str, str | None], list[str]] = {}
    for model_id, relations in model_relations.items():
        seen: set[tuple[str, str, str, str | None]] = set()
        for relation in relations:
            normalized = normalize_relation(relation)
            key = normalized.key
            exemplars.setdefault(key, relation)
            if key in seen:
                continue
            seen.add(key)
            voters.setdefault(key, set()).add(model_id)
            if relation.evidence:
                evidence.setdefault(key, []).append(relation.evidence)
    result: list[RoleTupleConsensus] = []
    for key, model_ids in voters.items():
        support = len(model_ids) / total_models
        if support < minimum_support:
            continue
        exemplar = exemplars[key]
        normalized = normalize_relation(exemplar)
        result.append(
            RoleTupleConsensus(
                actor=normalized.actor,
                relation=normalized.relation,
                target=normalized.target,
                condition=normalized.condition,
                support=support,
                supporting_models=tuple(sorted(model_ids)),
                evidence=tuple(dict.fromkeys(evidence.get(key, ()))),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                -item.support,
                item.key
                if hasattr(item, "key")
                else (item.actor, item.relation.value, item.target),
            ),
        )
    )


def tuple_set_similarity(
    expected: Iterable[RoleRelation], actual: Iterable[RoleRelation]
) -> dict[str, float]:
    """Return precision/recall/F1 over normalized complete relation tuples."""
    expected_keys = {normalize_relation(item).key for item in expected}
    actual_keys = {normalize_relation(item).key for item in actual}
    true_positive = len(expected_keys & actual_keys)
    precision = (
        true_positive / len(actual_keys) if actual_keys else (1.0 if not expected_keys else 0.0)
    )
    recall = (
        true_positive / len(expected_keys) if expected_keys else (1.0 if not actual_keys else 0.0)
    )
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def field_match_metrics(expected: RoleRelation, actual: RoleRelation) -> dict[str, bool]:
    """Expose actor/relation/target/evidence agreement independently for diagnostics."""
    return {
        "actor_match": _normalize_text(expected.actor) == _normalize_text(actual.actor),
        "relation_match": expected.relation == actual.relation,
        "target_match": _normalize_text(expected.target) == _normalize_text(actual.target),
        "evidence_match": _evidence_matches(expected.evidence, actual.evidence),
    }


def summarize_role_qualification(clauses: Iterable[Any]) -> RoleQualificationMetrics:
    """Summarize role-specific consensus fields on clause consensus objects."""
    items = tuple(clauses)
    return RoleQualificationMetrics(
        clause_count=len(items),
        candidate_clause_count=sum(bool(getattr(item, "role_candidate", False)) for item in items),
        positive_presence_clause_count=sum(
            bool(getattr(item, "role_semantics_present", False)) for item in items
        ),
        candidate_consensus_negative_count=sum(
            bool(getattr(item, "role_candidate", False))
            and not bool(getattr(item, "role_semantics_present", False))
            for item in items
        ),
        extracted_tuple_count=sum(
            len(getattr(item, "proposed_role_relations", ())) for item in items
        ),
        tuple_consensus_count=sum(
            len(getattr(item, "role_relation_consensus", ())) for item in items
        ),
    )


def _normalize_text(value: str | None) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip().casefold())
    return normalized.strip(" .,:;()[]{}")


def _evidence_matches(expected: str | None, actual: str | None) -> bool:
    if not expected and not actual:
        return True
    if not expected or not actual:
        return False
    left = _normalize_text(expected)
    right = _normalize_text(actual)
    return left == right or left in right or right in left
