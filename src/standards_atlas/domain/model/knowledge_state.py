"""Attribute-level availability, authority and derivation in canonical documents."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationMethod(StrEnum):
    SOURCE_EXTRACTION = "source_extraction"
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    IMPORTED = "imported"


class DecisionSupport(BaseModel):
    """Decision provenance, not a calibrated probability of correctness.

    Vote counts refer to the named source/stage, never to summed retries or
    repetitions. A policy or structural decision may have no numerical support.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str = Field(min_length=1)
    source_artifact: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage: str | None = None
    prompt_id: str | None = None
    reasoning_mode_id: str | None = None
    model_ids: tuple[str, ...] = ()
    valid_votes: int | None = Field(default=None, ge=0)
    supporting_votes: int | None = Field(default=None, ge=0)
    abstained_votes: int = Field(default=0, ge=0)
    label_votes: dict[str, int] = Field(default_factory=dict)
    category: str | None = None

    @model_validator(mode="after")
    def consistent_votes(self) -> DecisionSupport:
        if len(self.model_ids) != len(set(self.model_ids)):
            raise ValueError("decision model ids must be unique")
        counts = [*self.label_votes.values()]
        if self.supporting_votes is not None:
            counts.append(self.supporting_votes)
        if counts and (
            self.valid_votes is None
            or any(count < 0 or count > self.valid_votes for count in counts)
        ):
            raise ValueError("support counts require and cannot exceed valid_votes")
        return self


class GeneratedAttribute(BaseModel):
    """One selected, not yet authoritative attribute; missing is not False."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    generator: str = Field(min_length=1)
    method: GenerationMethod
    evidence: tuple[str, ...] = ()
    availability: Literal["known", "unknown"] = "known"
    decision: DecisionSupport | None = None


class ConfirmedAttribute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    authority: str = Field(default="explicit-confirmation", min_length=1)


def paths_overlap(left: str, right: str) -> bool:
    """Parent confirmations protect descendants as well as whole-object writes."""
    return left == right or left.startswith(right + ".") or right.startswith(left + ".")


class KnowledgeStateProvenance(BaseModel):
    """Attribute provenance. Absent metadata means not evaluated, not confirmed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_attributes: tuple[GeneratedAttribute, ...] = ()
    confirmed_attributes: tuple[ConfirmedAttribute, ...] = ()
    # Schema-8 values without provenance are preserved, not silently promoted.
    # An explicit confirmation can resolve these protected migration cases.
    unattributed_attributes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def generated_paths_are_unique(self) -> KnowledgeStateProvenance:
        for label, paths in (
            ("generated", [item.path for item in self.generated_attributes]),
            ("confirmed", [item.path for item in self.confirmed_attributes]),
            ("unattributed", list(self.unattributed_attributes)),
        ):
            if len(paths) != len(set(paths)):
                raise ValueError(f"{label} attribute paths must be unique")
        for item in self.generated_attributes:
            if self.protection(item.path):
                raise ValueError("generated attributes cannot also be protected")
        return self

    def protection(self, path: str) -> str | None:
        if any(paths_overlap(path, item.path) for item in self.confirmed_attributes):
            return "confirmed"
        if any(paths_overlap(path, item) for item in self.unattributed_attributes):
            return "unattributed"
        return None

    def availability(self, path: str) -> str:
        if self.protection(path):
            return "known"
        matches = [item for item in self.generated_attributes if paths_overlap(path, item.path)]
        if not matches:
            return "not_evaluated"
        return "known" if any(item.availability == "known" for item in matches) else "unknown"

    def mark_generated(self, *attributes: GeneratedAttribute) -> KnowledgeStateProvenance:
        by_path = {item.path: item for item in self.generated_attributes}
        for item in attributes:
            if self.protection(item.path):
                raise ValueError(f"cannot mark protected attribute generated: {item.path}")
            by_path[item.path] = item
        return self.model_copy(
            update={"generated_attributes": tuple(by_path[path] for path in sorted(by_path))}
        )

    def confirm_authoritative(
        self, *paths: str, authority: str = "explicit-confirmation"
    ) -> KnowledgeStateProvenance:
        confirmed = {item.path: item for item in self.confirmed_attributes}
        for path in paths:
            confirmed[path] = ConfirmedAttribute(path=path, authority=authority)
        return self.model_copy(
            update={
                "generated_attributes": tuple(
                    item
                    for item in self.generated_attributes
                    if not any(paths_overlap(item.path, path) for path in paths)
                ),
                "unattributed_attributes": tuple(
                    item
                    for item in self.unattributed_attributes
                    if not any(paths_overlap(item, path) for path in paths)
                ),
                "confirmed_attributes": tuple(confirmed[path] for path in sorted(confirmed)),
            }
        )
