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


class GemaraArtifactMapping(BaseModel):
    """Reference to an artifact or entry through a registered mapping reference."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    reference_id: str = Field(alias="reference-id", min_length=1)
    remarks: str | None = None


class GemaraMultiEntryMapping(BaseModel):
    """Relationship from one artifact entry to one or more referenced entries."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    reference_id: str = Field(alias="reference-id", min_length=1)
    entries: tuple[GemaraArtifactMapping, ...] = Field(min_length=1)


class GemaraMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    type: Literal["GuidanceCatalog", "ControlCatalog", "Policy"] = "GuidanceCatalog"
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


class GemaraAssessmentRequirement(BaseModel):
    """Verifiable requirement within a Gemara control."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    applicability: tuple[str, ...] = Field(min_length=1)
    recommendation: str | None = None
    state: Literal["Active", "Draft", "Deprecated", "Retired"] = "Active"


class GemaraControl(BaseModel):
    """Safeguard/countermeasure projected from qualified normative clauses."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    group: str = Field(min_length=1)
    assessment_requirements: tuple[GemaraAssessmentRequirement, ...] = Field(
        alias="assessment-requirements", min_length=1
    )
    guidelines: tuple[GemaraMultiEntryMapping, ...] | None = None
    state: Literal["Active", "Draft", "Deprecated", "Retired"] = "Active"


class GemaraControlCatalog(BaseModel):
    """Gemara ControlCatalog subset emitted by Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    metadata: GemaraMetadata
    groups: tuple[GemaraGroup, ...]
    controls: tuple[GemaraControl, ...] | None = None


class GemaraContact(BaseModel):
    """Gemara contact supplied explicitly for policy ownership."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    affiliation: str | None = None
    email: str | None = None
    social: str | None = None


class GemaraRaci(BaseModel):
    """Required policy ownership roles; never inferred from standards content."""

    model_config = ConfigDict(frozen=True)

    responsible: tuple[GemaraContact, ...] = Field(min_length=1)
    accountable: tuple[GemaraContact, ...] = Field(min_length=1)
    consulted: tuple[GemaraContact, ...] | None = None
    informed: tuple[GemaraContact, ...] | None = None


class GemaraPolicyDimensions(BaseModel):
    """Gemara policy scope dimensions projected from governance context."""

    model_config = ConfigDict(frozen=True)

    technologies: tuple[str, ...] | None = None
    geopolitical: tuple[str, ...] | None = None
    sensitivity: tuple[str, ...] | None = None
    users: tuple[str, ...] | None = None
    groups: tuple[str, ...] | None = None


class GemaraPolicyScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    in_: GemaraPolicyDimensions = Field(alias="in")
    out: GemaraPolicyDimensions | None = None


class GemaraCatalogImport(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    reference_id: str = Field(alias="reference-id", min_length=1)
    exclusions: tuple[str, ...] | None = None


class GemaraGuidanceImport(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    reference_id: str = Field(alias="reference-id", min_length=1)
    exclusions: tuple[str, ...] | None = None


class GemaraPolicyImports(BaseModel):
    model_config = ConfigDict(frozen=True)

    catalogs: tuple[GemaraCatalogImport, ...] | None = None
    guidance: tuple[GemaraGuidanceImport, ...] | None = None


class GemaraPolicyAdherence(BaseModel):
    """Empty authoring boundary until evaluation details are supplied externally."""

    model_config = ConfigDict(frozen=True)


class GemaraPolicy(BaseModel):
    """Gemara Policy scaffold emitted from reviewed governance candidates."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    title: str = Field(min_length=1)
    metadata: GemaraMetadata
    contacts: GemaraRaci
    scope: GemaraPolicyScope
    imports: GemaraPolicyImports
    adherence: GemaraPolicyAdherence = Field(default_factory=GemaraPolicyAdherence)
