"""Explicit experimental policies for partial cascades, never implicit defaults.

Profiles change acceptance, not observations or source authority. Fractions are
compared as integer ratios. Lexical anchoring is a conservative veto safeguard,
not proof that a role assertion is semantically correct or incorrect.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
)


class FocusedResolutionPolicy(BaseModel):
    """One bounded re-questioning round, using existing first-stage voters only."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    max_cases: int = Field(default=12, ge=0, le=500)
    max_requests: int = Field(default=24, ge=0, le=1000)
    max_output_tokens: int = Field(default=384, ge=64, le=1024)
    max_total_output_tokens: int = Field(default=9216, ge=0, le=1024000)
    models_per_case: int = Field(default=2, ge=1, le=2)


class PartialAcceptanceProfile(SchemaBoundModel):
    """Versioned opt-in policy; empirical release is a separate qualification."""

    SCHEMA_FAMILY: ClassVar[str] = "partial-acceptance-profile"

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    manifest_type: Literal["partial-cascade-acceptance-profile"] = (
        "partial-cascade-acceptance-profile"
    )
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]*$")
    version: Literal["1.0.0"] = "1.0.0"
    qualification_status: Literal["experimental"] = "experimental"
    statement_two_thirds: bool = False
    role_evidence_mode: Literal["legacy_veto", "anchored_minority"] = "legacy_veto"
    applicability_gate_mode: Literal["legacy", "positive_three_quarters"] = "legacy"
    focused_resolution: FocusedResolutionPolicy | None = None

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))

    @classmethod
    def load(cls, path: Path) -> PartialAcceptanceProfile:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        # JSON validation retains strict scalar checking and accepts JSON containers.
        return cls.model_validate_json(json.dumps(payload, allow_nan=False))


class ProfiledResolution(CascadeResolutionConfig):
    """Runtime extension; old manifests and their serialized defaults stay intact."""

    partial_acceptance: PartialAcceptanceProfile


def with_acceptance_profile(
    resolution: CascadeResolutionConfig, profile: PartialAcceptanceProfile | None
) -> CascadeResolutionConfig:
    if profile is None:
        return resolution
    payload = resolution.model_dump()
    existing = payload.pop("partial_acceptance", None)
    if existing is not None and existing != profile.model_dump():
        raise ValueError("acceptance profile changed on an already profiled resolution")
    return ProfiledResolution(**payload, partial_acceptance=profile)


def profile_from_plan(plan: dict[str, Any]) -> PartialAcceptanceProfile | None:
    payload = plan.get("acceptance_profile")
    if payload is None:
        return None
    return PartialAcceptanceProfile.model_validate_json(json.dumps(payload, allow_nan=False))


def experimental_threshold(
    *,
    attribute: str,
    candidate: Any,
    resolution: CascadeResolutionConfig,
    majority_threshold: float,
    original_threshold: float,
    unanimity: bool,
) -> tuple[Fraction, bool, tuple[str, ...]]:
    """Return one threshold for both review and routing; preserve model minima."""
    profile = getattr(resolution, "partial_acceptance", None)
    threshold = Fraction(str(original_threshold))
    if profile is None:
        return threshold, unanimity, ()
    rules = []
    if (
        profile.statement_two_thirds
        and attribute == "primary_function"
        and resolution.statement_function_resolution_mode != "stage_resolver"
    ):
        # Replace only the decimal review boundary; keep an explicitly higher
        # stage/model consensus floor and do not relax stage-local final resolvers.
        threshold = max(
            Fraction(2, 3),
            Fraction(str(resolution.minimum_confidence)),
            Fraction(str(majority_threshold)),
        )
        rules.append("statement_exact_two_thirds")
    if profile.role_evidence_mode == "anchored_minority" and attribute == "role_semantics_present":
        threshold = max(Fraction(3, 4), Fraction(str(majority_threshold)))
        unanimity = False
        rules.append("role_three_quarters_with_evidence_guard")
    if (
        profile.applicability_gate_mode == "positive_three_quarters"
        and attribute == "applicability_present"
    ):
        # Positive decisions only open detail processing; a dissenting positive
        # vote cannot be closed as an early negative by this profile.
        threshold = max(Fraction(3, 4), Fraction(str(majority_threshold)))
        unanimity = candidate is False
        rules.append("positive_gate_three_quarters_negative_unanimity")
    return threshold, unanimity, tuple(rules)


def _words(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", value.casefold()))


def _contains_words(text: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    return bool(phrase) and any(
        text[i : i + len(phrase)] == phrase for i in range(len(text) - len(phrase) + 1)
    )


def assess_role_minority(relation_values: dict[str, Any], *, text: str) -> dict[str, Any]:
    """Classify stored suggestions without deleting, endorsing or inventing them.

    A literal actor in the clause is enough to retain the protective veto, even
    when the target is paraphrased. Independently repeated identical assertions
    retain it too. Absence of a literal actor is NOT evidence of semantic absence.
    Only valid, actually observed RoleRelation objects enter this function.
    """
    source = _words(text)
    supports: dict[str, set[str]] = defaultdict(set)
    relations = {}
    anchored = set()
    for model, items in relation_values.items():
        for relation in items:
            identity = json.dumps(relation, sort_keys=True, ensure_ascii=False)
            supports[identity].add(model)
            relations[identity] = relation
            if _contains_words(source, _words(relation["actor"])):
                anchored.add(identity)
    corroborated = {key for key, voters in supports.items() if len(voters) >= 2}
    return {
        "suggestion_count": len(relations),
        "literal_actor_count": len(anchored),
        "corroborated_suggestion_count": len(corroborated),
        "protective_veto": bool(anchored or corroborated),
        "semantic_truth_verified": False,
    }
