"""Knowledge-state provenance for canonical engineering documents."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationMethod(StrEnum):
    """Method used to create a generated, not-yet-authoritative attribute."""

    SOURCE_EXTRACTION = "source_extraction"
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    IMPORTED = "imported"


class GeneratedAttribute(BaseModel):
    """Provenance for one non-authoritative attribute in the knowledge state.

    ``path`` is relative to the containing clause and addresses either the
    deterministic ``baseline`` or the derived ``enrichments`` block.
    Generated attributes remain auditable until an authoritative source such
    as curated AtlasData confirms or replaces them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    generator: str = Field(min_length=1)
    method: GenerationMethod
    evidence: tuple[str, ...] = ()


class KnowledgeStateProvenance(BaseModel):
    """Attribute-level provenance for generated knowledge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_attributes: tuple[GeneratedAttribute, ...] = ()

    @model_validator(mode="after")
    def generated_paths_are_unique(self) -> KnowledgeStateProvenance:
        paths = [item.path for item in self.generated_attributes]
        if len(paths) != len(set(paths)):
            raise ValueError("generated attribute paths must be unique")
        return self

    def mark_generated(self, *attributes: GeneratedAttribute) -> KnowledgeStateProvenance:
        """Return provenance with the supplied generated attributes upserted by path."""
        by_path = {item.path: item for item in self.generated_attributes}
        by_path.update({item.path: item for item in attributes})
        return self.model_copy(
            update={"generated_attributes": tuple(by_path[path] for path in sorted(by_path))}
        )

    def confirm_authoritative(self, *paths: str) -> KnowledgeStateProvenance:
        """Return provenance after authoritative confirmation of the supplied paths."""
        confirmed = set(paths)
        return self.model_copy(
            update={
                "generated_attributes": tuple(
                    item for item in self.generated_attributes if item.path not in confirmed
                )
            }
        )
