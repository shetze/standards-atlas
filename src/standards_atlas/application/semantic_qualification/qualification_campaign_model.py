"""Versioned, opt-in qualification campaign. No labels enter model requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
)


class CampaignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class CampaignVariant(CampaignModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    matrix: Path
    prompt: str = "taxonomy-partial-v2"
    acceptance_profile: Path | None = None
    change: str = Field(min_length=1)
    require_taxonomy_decisions: bool = Field(default=False, strict=True)


QUALIFICATION_MANIFEST_SCHEMA_VERSION = "1.1"


class QualificationCampaign(CampaignModel):
    """Plan the comparisons first; never pick a winning policy after seeing labels."""

    model_config = ConfigDict(revalidate_instances="always")

    schema_version: Literal["1.1"]
    manifest_type: Literal["partial_qualification"] = "partial_qualification"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    run: Path | None = None
    dataset: Path | None = None
    golden: Path
    variants: tuple[CampaignVariant, ...] = Field(min_length=2)
    baseline: str
    candidate: str
    sample_size: int = Field(default=200, ge=1, strict=True)
    seed: int = Field(default=20260913, strict=True)
    repetitions: int = Field(default=3, ge=3, strict=True)
    minimum_published_golden_cases: int = Field(default=116, ge=116, strict=True)
    semantic_suites: tuple[Path, ...] = ()
    # Relative to THIS manifest; other input paths remain project-root relative.
    review_bundle: Path | None = None
    sentinel_suites: tuple[Path, ...] = ()
    required_semantic_attributes: tuple[str, ...] = (
        "primary_function",
        "primary_knowledge_kind",
        "role_semantics_present",
        "process_functions",
    )
    max_semantic_errors: int = Field(default=0, ge=0, strict=True)
    max_semantic_unavailable: int = Field(default=0, ge=0, strict=True)
    max_request_ratio: float = Field(default=1.10, gt=0, strict=True)
    efficient_target: float = Field(default=0.8, ge=0.8, le=1)

    @model_validator(mode="after")
    def valid_campaign(self):
        if self.review_bundle is not None and self.semantic_suites:
            raise ValueError("review_bundle replaces semantic_suites")
        if (self.run is None) == (self.dataset is None):
            raise ValueError("campaign requires exactly one source: run or dataset")
        names = [v.id for v in self.variants]
        if (
            len(set(names)) != len(names)
            or any(name not in names for name in (self.baseline, self.candidate))
            or self.baseline == self.candidate
        ):
            raise ValueError("unique variants and distinct existing baseline/candidate required")
        if (
            not self.required_semantic_attributes
            or len(set(self.required_semantic_attributes)) != len(self.required_semantic_attributes)
            or any(a not in PARTIAL_ATTRIBUTES for a in self.required_semantic_attributes)
        ):
            raise ValueError("required semantic attributes must be unique current attributes")
        mandatory = {
            "primary_function",
            "primary_knowledge_kind",
            "role_semantics_present",
            "process_functions",
        }
        if not mandatory <= set(self.required_semantic_attributes):
            raise ValueError("release semantic coverage cannot omit core dimensions")
        return self

    @classmethod
    def load(cls, path: Path):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("qualification campaign manifest must contain a mapping")
        require_supported_schema("partial-qualification-manifest", data.get("schema_version"))
        # Only the handoff pointer is manifest-relative; other inputs stay project-relative.
        if data.get("review_bundle") is not None:
            pointer = Path(data["review_bundle"])
            data["review_bundle"] = str((path.parent / pointer).absolute())
        # Relative paths intentionally follow existing matrix/CLI project-root semantics.
        return cls.model_validate(data)


class SemanticPredicate(CampaignModel):
    equals: Any = None
    must_include: tuple[str, ...] | None = None
    must_be_empty: bool | None = None

    @model_validator(mode="after")
    def one_operator(self):
        if len(self.model_fields_set) != 1:
            raise ValueError("semantic predicate requires exactly one explicit operator")
        if "must_include" in self.model_fields_set and not self.must_include:
            raise ValueError("must_include requires labels")
        if "must_be_empty" in self.model_fields_set and self.must_be_empty is not True:
            raise ValueError("must_be_empty must be true")
        return self


class SemanticReferenceCase(CampaignModel):
    example_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    attributes: dict[str, SemanticPredicate] = Field(min_length=1)

    @model_validator(mode="after")
    def known_attributes(self):
        if any(a not in PARTIAL_ATTRIBUTES for a in self.attributes):
            raise ValueError("unknown semantic reference attribute")
        return self


class SemanticReferenceSuite(CampaignModel):
    """Independent review is a declared provenance claim, not generated by software."""

    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-semantic-reference"] = "partial-semantic-reference"
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    split: Literal["development", "holdout"]
    status: Literal["draft", "published"] = "draft"
    reviewed_by: str | None = None
    review_reference: str | None = None
    cases: tuple[SemanticReferenceCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def review_and_uniqueness(self):
        if len({c.example_id for c in self.cases}) != len(self.cases):
            raise ValueError("duplicate semantic reference identity")
        if self.status == "published" and not (
            self.reviewed_by
            and self.reviewed_by.strip()
            and self.review_reference
            and self.review_reference.strip()
        ):
            raise ValueError("published semantic suite requires explicit review provenance")
        return self


def predicate_passes(actual: Any, predicate: SemanticPredicate) -> bool:
    from standards_atlas.application.semantic_qualification.semantic_readiness import _value_key

    if "equals" in predicate.model_fields_set:
        return _value_key(actual) == _value_key(predicate.equals)
    if predicate.must_be_empty:
        return isinstance(actual, list) and not actual
    return isinstance(actual, list) and set(predicate.must_include or ()) <= set(actual)
