"""Source-only structural observations for qualification (never semantic answers).

This additive transport contract does not change EngineeringDocument persistence.
An unattributed baseline value is observable, not automatically authoritative.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

StructureField = Literal[
    "clause_type",
    "heading",
    "parent_id",
    "canonical_section",
    "document_categories",
    "domain_categories",
    "semantic_sections",
    "node_kind",
    "child_clause_ids",
    "ancestor_heading",
    "annex_status",
]
StructureOrigin = Literal[
    "confirmed",
    "deterministic",
    "source_extraction",
    "unattributed",
    "unavailable",
    "excluded",
]

SOURCE_PATHS = {
    "clause_type": "clause_type",
    "heading": "baseline.heading",
    "parent_id": "baseline.parent_id",
    "canonical_section": "baseline.structural_profile.canonical_section",
    "document_categories": "baseline.structural_profile.document_categories",
    "domain_categories": "baseline.structural_profile.domain_categories",
    "semantic_sections": "baseline.structural_profile.semantic_sections",
    "annex_status": "baseline.structural_profile.annex_status",
    "node_kind": "baseline.structural_context.node_kind",
    "child_clause_ids": "baseline.structural_context.child_clause_ids",
    "ancestor_heading": "baseline.heading",
}


def structure_fingerprint(value: object) -> str:
    """Stable semantic JSON identity, independent of rendering and key order."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class SourceStructureFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: StructureField
    value: JsonValue
    source_clause_id: str = Field(min_length=1)
    source_reference: str
    source_path: str
    origin: StructureOrigin = "unattributed"
    generator: str | None = None
    authority: str | None = None
    evidence: tuple[str, ...] = ()
    # Ancestor distance is explicit, with the immediate parent at distance 1.
    distance: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_source(self) -> SourceStructureFact:
        if self.source_path != SOURCE_PATHS[self.field]:
            raise ValueError("source structure facts must address the allowlisted baseline path")
        if (self.field == "ancestor_heading") != (self.distance > 0):
            raise ValueError("only ancestor headings carry a positive distance")
        if self.origin == "confirmed" and not self.authority:
            raise ValueError("confirmed source structure needs an authority")
        if self.origin in {"deterministic", "source_extraction"} and not self.generator:
            raise ValueError("generated source structure needs a generator")
        if self.origin in {"excluded", "unavailable"} and self.value is not None:
            raise ValueError("excluded/unknown facts must not expose an interpretation")
        if self.value is not None:
            if self.field in {
                "heading",
                "ancestor_heading",
                "clause_type",
                "parent_id",
                "canonical_section",
                "annex_status",
                "node_kind",
            } and not isinstance(self.value, str):
                raise ValueError("scalar structure fields require a string or explicit None")
            if self.field in {
                "document_categories",
                "domain_categories",
                "semantic_sections",
                "child_clause_ids",
            }:
                if not isinstance(self.value, list):
                    raise ValueError("collection structure fields require an explicit list")
                allowed = (
                    {"label", "role", "start_offset", "end_offset"}
                    if self.field == "semantic_sections"
                    else {"taxonomy", "version", "category"}
                )
                for item in self.value:
                    if isinstance(item, dict):
                        if self.field == "child_clause_ids" or set(item) - allowed:
                            raise ValueError("non-structural fields inside source structure")
                        if any(isinstance(value, (dict, list)) for value in item.values()):
                            raise ValueError("nested interpretation is not structural evidence")
                    elif not isinstance(item, str):
                        raise ValueError("invalid structure collection entry")
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))


class SourceStructure(BaseModel):
    """The reader can audit exactly which canonical structural facts were observed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    origin: Literal["canonical", "legacy-context"] = "canonical"
    facts: tuple[SourceStructureFact, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def stable_fact_order(cls, payload: object) -> object:
        if isinstance(payload, dict) and "facts" in payload:

            def key(fact: object) -> tuple:
                if isinstance(fact, SourceStructureFact):
                    return fact.field, fact.distance
                return fact.get("field", ""), fact.get("distance", 0)

            return {**payload, "facts": sorted(payload["facts"], key=key)}
        return payload

    @model_validator(mode="after")
    def validate_identity(self) -> SourceStructure:
        keys = [(fact.field, fact.distance) for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate source structure field/distance")
        for fact in self.facts:
            if fact.distance == 0 and (
                fact.source_clause_id != self.clause_id or fact.source_reference != self.reference
            ):
                raise ValueError("local structure fact belongs to another clause")
            if fact.distance > 0 and fact.source_clause_id == self.clause_id:
                raise ValueError("a clause cannot be its own ancestor")
            if self.origin == "legacy-context" and fact.origin != "unattributed":
                raise ValueError("legacy context cannot acquire canonical source authority")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["facts"] = sorted(
            payload["facts"], key=lambda fact: (fact["field"], fact["distance"])
        )
        return structure_fingerprint(payload)
