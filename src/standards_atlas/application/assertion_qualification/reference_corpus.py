"""AP03 Series-D grouped reference-corpus planning without semantic annotation.

Selection is deliberately separate from Golden truth.  It operates on source-group and
exposure metadata only; expected entities/assertions remain pending until human review.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExposureKind(StrEnum):
    LEGACY_DEVELOPMENT = "legacy_development"
    AP02_SYNTHETIC = "ap02_synthetic"
    PRIOR_HUMAN_REVIEW = "prior_human_review"
    PROMPT_EXAMPLE = "prompt_example"
    OPTIMIZATION = "optimization"
    DIAGNOSIS = "diagnosis"
    CODEX_SESSION = "codex_session"
    UNKNOWN = "unknown"


class ReferenceExposure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: ExposureKind
    reference: str = Field(min_length=1)
    detail: str = ""


class ReferenceCandidate(BaseModel):
    """One processable clause plus all source groups that can carry its interpretation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    clause_type: str = Field(min_length=1)
    primary_source_group: str = Field(min_length=1)
    bearing_source_groups: tuple[str, ...] = Field(min_length=1)
    traits: tuple[str, ...] = ()
    eligible: bool = True
    eligibility_reason: str | None = None
    exposures: tuple[ReferenceExposure, ...] = ()

    @model_validator(mode="after")
    def source_groups_are_complete(self):
        if self.primary_source_group not in self.bearing_source_groups:
            raise ValueError("primary_source_group must be included in bearing_source_groups")
        if len(self.bearing_source_groups) != len(set(self.bearing_source_groups)):
            raise ValueError("bearing_source_groups must be unique")
        return self

    @property
    def key(self) -> str:
        return f"{self.document_key}:{self.clause_id}"


class ReferenceCorpusRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    plan_id: str = Field(min_length=1)
    plan_version: str = Field(min_length=1)
    seed: int
    development_limit: int = Field(ge=1)
    holdout_limit: int = Field(ge=1)
    candidates: tuple[ReferenceCandidate, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_cases(self):
        keys = [c.key for c in self.candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("reference corpus candidate keys must be unique")
        return self


class PlannedReferenceCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    document_key: str
    clause_id: str
    reference: str
    partition: Literal["development", "holdout"]
    source_group: str
    bearing_source_groups: tuple[str, ...]
    traits: tuple[str, ...]
    expected_status: Literal["pending"] = "pending"


class ExposureRegisterEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    document_key: str
    clause_id: str
    source_group: str
    exposures: tuple[ReferenceExposure, ...]
    holdout_independence_eligible: bool
    blockers: tuple[str, ...] = ()


class ReferenceCorpusPlan(BaseModel):
    """Text-free reproducible partition/exposure manifest; not a Golden suite."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    contract_id: Literal["assertion-reference-corpus-plan-v1"] = (
        "assertion-reference-corpus-plan-v1"
    )
    plan_id: str
    plan_version: str
    seed: int
    selection_method: Literal["bearing-source-group-diversity-v1"] = (
        "bearing-source-group-diversity-v1"
    )
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development: tuple[PlannedReferenceCase, ...]
    holdout: tuple[PlannedReferenceCase, ...]
    exposure_register: tuple[ExposureRegisterEntry, ...]
    excluded: dict[str, str]
    blockers: tuple[str, ...] = ()
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="before")
    @classmethod
    def plan_hash_matches_serialized_content(cls, value):
        # Verify the hash against the JSON-shaped payload as supplied, before Pydantic
        # normalizes lists/tuples/enums.  This is the same canonical form written by
        # the S07 CLI and avoids a verifier that hashes a different representation
        # from the producer.
        if isinstance(value, dict) and "plan_sha256" in value:
            stored = value.get("plan_sha256")
            body = {key: item for key, item in value.items() if key != "plan_sha256"}
            expected = _canonical_sha256(body)
            if stored != expected:
                raise ValueError(
                    "reference corpus plan_sha256 does not match plan content; "
                    f"stored={stored}, expected={expected}. "
                    "Regenerate partition-and-exposure.json with "
                    "'standards-atlas evaluation assertion-reference-corpus-plan' "
                    "from the original corpus request and do not edit the generated plan."
                )
        return value

    @model_validator(mode="after")
    def partitions_are_disjoint(self):
        dev = {c.source_group for c in self.development}
        hold = {c.source_group for c in self.holdout}
        if dev & hold:
            raise ValueError("development and holdout source groups overlap")
        if any(c.expected_status != "pending" for c in (*self.development, *self.holdout)):
            raise ValueError("corpus planning cannot publish expected knowledge")
        return self


def _canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _connected_groups(candidates: tuple[ReferenceCandidate, ...]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for case in candidates:
        groups = case.bearing_source_groups
        for group in groups:
            find(group)
        for group in groups[1:]:
            union(groups[0], group)
    return {group: find(group) for group in parent}


def _holdout_blockers(cases: list[ReferenceCandidate]) -> tuple[str, ...]:
    blockers: set[str] = set()
    for case in cases:
        for exposure in case.exposures:
            if exposure.kind in {
                ExposureKind.LEGACY_DEVELOPMENT,
                ExposureKind.AP02_SYNTHETIC,
                ExposureKind.PRIOR_HUMAN_REVIEW,
                ExposureKind.PROMPT_EXAMPLE,
                ExposureKind.OPTIMIZATION,
                ExposureKind.DIAGNOSIS,
                ExposureKind.CODEX_SESSION,
                ExposureKind.UNKNOWN,
            }:
                blockers.add(exposure.kind.value)
    return tuple(sorted(blockers))


def _ordered_groups(groups: dict[str, list[ReferenceCandidate]], seed: int) -> list[str]:
    rng = random.Random(seed)
    decorated = []
    for group, cases in groups.items():
        traits = {trait for case in cases for trait in case.traits}
        # Diversity first, deterministic pseudo-random tie-break second.
        decorated.append((-len(traits), rng.random(), group))
    decorated.sort()
    return [group for _, _, group in decorated]


def _take_groups(
    groups: dict[str, list[ReferenceCandidate]], order: list[str], limit: int, partition: str
) -> tuple[list[PlannedReferenceCase], set[str]]:
    selected: list[PlannedReferenceCase] = []
    used: set[str] = set()
    for group in order:
        if len(selected) >= limit:
            break
        cases = sorted(groups[group], key=lambda c: (c.document_key, c.reference, c.clause_id))
        room = limit - len(selected)
        for case in cases[:room]:
            selected.append(
                PlannedReferenceCase(
                    document_key=case.document_key,
                    clause_id=case.clause_id,
                    reference=case.reference,
                    partition=partition,
                    source_group=group,
                    bearing_source_groups=case.bearing_source_groups,
                    traits=case.traits,
                )
            )
        used.add(group)
    return selected, used


def build_reference_corpus_plan(request: ReferenceCorpusRequest) -> ReferenceCorpusPlan:
    """Create disjoint Development/Holdout selections without creating annotations."""
    roots = _connected_groups(request.candidates)
    grouped: dict[str, list[ReferenceCandidate]] = defaultdict(list)
    excluded: dict[str, str] = {}
    for candidate in request.candidates:
        if not candidate.eligible:
            excluded[candidate.key] = candidate.eligibility_reason or "not_eligible"
            continue
        root = roots[candidate.primary_source_group]
        grouped[root].append(candidate)

    exposure_entries: list[ExposureRegisterEntry] = []
    holdout_allowed: dict[str, list[ReferenceCandidate]] = {}
    development_groups: dict[str, list[ReferenceCandidate]] = {}
    for group, cases in grouped.items():
        blockers = _holdout_blockers(cases)
        development_groups[group] = cases
        if not blockers:
            holdout_allowed[group] = cases
        for case in cases:
            exposure_entries.append(
                ExposureRegisterEntry(
                    document_key=case.document_key,
                    clause_id=case.clause_id,
                    source_group=group,
                    exposures=case.exposures,
                    holdout_independence_eligible=not blockers,
                    blockers=blockers,
                )
            )

    # Reserve independent groups for holdout before widening Development.
    hold_order = _ordered_groups(holdout_allowed, request.seed ^ 0xA503)
    holdout, hold_groups = _take_groups(
        holdout_allowed, hold_order, request.holdout_limit, "holdout"
    )
    dev_pool = {k: v for k, v in development_groups.items() if k not in hold_groups}
    dev_order = _ordered_groups(dev_pool, request.seed ^ 0xD307)
    development, _ = _take_groups(dev_pool, dev_order, request.development_limit, "development")

    blockers: list[str] = []
    if len(holdout) < request.holdout_limit:
        blockers.append(
            f"independent holdout shortfall: selected {len(holdout)} of {request.holdout_limit}"
        )
    if len(development) < request.development_limit:
        blockers.append(
            f"development shortfall: selected {len(development)} of {request.development_limit}"
        )

    candidate_payload = [c.model_dump(mode="json") for c in request.candidates]
    body = {
        "contract_id": "assertion-reference-corpus-plan-v1",
        "plan_id": request.plan_id,
        "plan_version": request.plan_version,
        "seed": request.seed,
        "selection_method": "bearing-source-group-diversity-v1",
        "candidate_sha256": _canonical_sha256(candidate_payload),
        "development": [c.model_dump(mode="json") for c in development],
        "holdout": [c.model_dump(mode="json") for c in holdout],
        "exposure_register": [e.model_dump(mode="json") for e in exposure_entries],
        "excluded": excluded,
        "blockers": blockers,
    }
    return ReferenceCorpusPlan(**body, plan_sha256=_canonical_sha256(body))
