"""Gemara GuidanceCatalog projection models.

These models intentionally mirror only the subset emitted by Standards Atlas.
They are adapter-facing contracts, not part of the canonical knowledge state.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GemaraActor(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: Literal["Human", "Software", "Software Assisted"]
    version: str | None = None
    description: str | None = None
    uri: str | None = None


class GemaraGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class GemaraMappingReference(BaseModel):
    """Reference to one external artifact registered in Gemara metadata."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None
    url: str | None = None


class GemaraMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    type: Literal["GuidanceCatalog"] = "GuidanceCatalog"
    gemara_version: str = Field(alias="gemara-version", min_length=1)
    version: str | None = None
    description: str = Field(min_length=1)
    author: GemaraActor
    mapping_references: tuple[GemaraMappingReference, ...] | None = Field(
        default=None, alias="mapping-references"
    )
    applicability_groups: tuple[GemaraGroup, ...] | None = Field(
        default=None, alias="applicability-groups"
    )
    draft: bool | None = None


class GemaraStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str | None = None
    text: str = Field(min_length=1)
    recommendations: tuple[str, ...] | None = None


class GemaraRationale(BaseModel):
    model_config = ConfigDict(frozen=True)

    importance: str = Field(min_length=1)
    goals: tuple[str, ...] = Field(min_length=1)


class GemaraGuideline(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    group: str = Field(min_length=1)
    recommendations: tuple[str, ...] | None = None
    applicability: tuple[str, ...] | None = None
    rationale: GemaraRationale | None = None
    statements: tuple[GemaraStatement, ...] | None = None
    see_also: tuple[str, ...] | None = Field(default=None, alias="see-also")
    state: Literal["Active", "Draft", "Deprecated", "Retired"] = "Active"


class GemaraGuidanceCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    title: str = Field(min_length=1)
    metadata: GemaraMetadata
    type: Literal["Standard", "Regulation", "Best Practice", "Framework"] = "Standard"
    front_matter: str | None = Field(default=None, alias="front-matter")
    groups: tuple[GemaraGroup, ...]
    guidelines: tuple[GemaraGuideline, ...] | None = None
