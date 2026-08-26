from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationType(StrEnum):
    SECTOR_SPECIALIZATION_OF = "sector-specialization-of"
    DERIVED_FROM = "derived-from"
    COMPLEMENTS = "complements"
    DEPENDS_ON = "depends-on"
    RELATED_TO = "related-to"
    PROVIDES_METHOD_FOR = "provides-method-for"
    SUPPLEMENTS = "supplements"
    SUPERSEDES = "supersedes"
    SUPERSEDED_BY = "superseded-by"
    ADAPTS = "adapts"
    SPECIALIZES = "specializes"
    CONSOLIDATES = "consolidates"


class NormativeState(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"
    DRAFT = "draft"
    HISTORICAL = "historical"


class StandardStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    normative_state: NormativeState = NormativeState.CURRENT
    effective_from: int | None = None
    effective_until: int | None = None
    retained_for: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_period(self) -> StandardStatus:
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until must not precede effective_from")
        return self


class StandardScope(BaseModel):
    model_config = ConfigDict(frozen=True)
    sectors: tuple[str, ...] = ()
    railway_domains: tuple[str, ...] = ()
    lifecycle_areas: tuple[str, ...] = ()
    note: str | None = None


class StandardLineage(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    members: tuple[str, ...]
    knowledge_domains: tuple[str, ...] = ()
    industry_sectors: tuple[str, ...] = ()


class KnowledgeDomain(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    parent: str | None = None


class IndustrySector(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    parent: str | None = None


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)
    knowledge_domains: tuple[str, ...] = ()
    industry_sectors: tuple[str, ...] = ()


class StandardRelation(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: RelationType
    target: str
    note: str | None = None


class PageRange(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: int = Field(ge=1)
    end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> PageRange:
        if self.end is not None and self.end < self.start:
            raise ValueError("page range end must not precede start")
        return self


class ContentSelection(BaseModel):
    model_config = ConfigDict(frozen=True)
    language: str | None = None
    page_ranges: tuple[PageRange, ...] = ()
    exclude_page_ranges: tuple[PageRange, ...] = ()
    page_list: str | None = None

    @model_validator(mode="after")
    def validate_page_list(self) -> ContentSelection:
        if self.page_list is not None:
            parse_page_list(self.page_list)
        return self


def parse_page_list(value: str) -> tuple[int, ...]:
    """Parse a one-based comma-separated page list such as ``1,3,5-7``."""
    pages: set[int] = set()
    for raw_token in value.split(","):
        token = raw_token.strip()
        if not token:
            raise ValueError("page_list must not contain empty entries")
        if "-" in token:
            try:
                start_text, end_text = token.split("-", maxsplit=1)
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise ValueError(
                    f"invalid page_list entry {token!r}; expected PAGE or START-END"
                ) from exc
            if start < 1 or end < start:
                raise ValueError(f"invalid page_list range {token!r}")
            pages.update(range(start, end + 1))
        else:
            try:
                page = int(token)
            except ValueError as exc:
                raise ValueError(
                    f"invalid page_list entry {token!r}; expected PAGE or START-END"
                ) from exc
            if page < 1:
                raise ValueError(f"invalid page number {page}; pages are one-based")
            pages.add(page)
    if not pages:
        raise ValueError("page_list must select at least one page")
    return tuple(sorted(pages))


class SourceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    pdf: Path


class AtlasDataDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    path: Path
    mode: str = "existing"


class DoorstopIdentifierDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    width: int = Field(default=8, ge=1)


class DoorstopExportDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    enabled: bool = True
    identifier: DoorstopIdentifierDefinition = Field(default_factory=DoorstopIdentifierDefinition)


class ExportDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    markdown: bool = True
    doorstop: DoorstopExportDefinition = Field(default_factory=DoorstopExportDefinition)


class DocumentType(StrEnum):
    STANDARD = "standard"
    TECHNICAL_SPECIFICATION = "technical-specification"
    TECHNICAL_REPORT = "technical-report"
    AMENDMENT = "amendment"
    CORRIGENDUM = "corrigendum"


class StandardSupplementDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    supplement: str
    key: str
    title: str | None = None
    publication_year: int | None = None
    document_type: DocumentType = DocumentType.TECHNICAL_SPECIFICATION
    source: SourceDefinition
    classification: Classification = Field(default_factory=Classification)
    relations: tuple[StandardRelation, ...] = ()
    content_selection: ContentSelection | None = None
    atlasdata: AtlasDataDefinition | None = None


class StandardPartDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    part: str
    key: str
    title: str | None = None
    publication_year: int | None = None
    source: SourceDefinition
    classification: Classification = Field(default_factory=Classification)
    content_selection: ContentSelection | None = None
    supplements: tuple[StandardSupplementDefinition, ...] = ()


class StandardFamilyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    organization: str
    publication_year: int | None = None
    title: str | None = None
    source: SourceDefinition | None = None
    content_selection: ContentSelection | None = None
    parts: tuple[StandardPartDefinition, ...] = ()
    classification: Classification = Field(default_factory=Classification)
    relations: tuple[StandardRelation, ...] = ()
    status: StandardStatus = Field(default_factory=StandardStatus)
    scope: StandardScope = Field(default_factory=StandardScope)
    atlasdata: AtlasDataDefinition | None = None
    exports: ExportDefinition = Field(default_factory=ExportDefinition)

    @model_validator(mode="after")
    def validate_source_shape(self) -> StandardFamilyDefinition:
        if (self.source is None) == (not self.parts):
            raise ValueError("family must define either source or parts")
        return self


class StandardProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    families: tuple[str, ...]
    knowledge_domains: tuple[str, ...] = ()
    industry_sectors: tuple[str, ...] = ()


class DoorstopHierarchyDefinition(BaseModel):
    """A deterministic Doorstop tree projected from the Knowledge Domain graph."""

    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    root: str
    families: tuple[str, ...]
    template: str = "atlas-clean"

    @model_validator(mode="after")
    def validate_root_member(self) -> DoorstopHierarchyDefinition:
        if self.root not in self.families:
            raise ValueError("doorstop hierarchy root must be one of its families")
        if len(set(self.families)) != len(self.families):
            raise ValueError("doorstop hierarchy families must be unique")
        return self


class StandardCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)
    manifest_type: Literal["standards"] = "standards"
    schema_version: Literal[2] = 2
    knowledge_domains: tuple[KnowledgeDomain, ...]
    industry_sectors: tuple[IndustrySector, ...]
    families: tuple[StandardFamilyDefinition, ...]
    profiles: tuple[StandardProfile, ...] = ()
    lineages: tuple[StandardLineage, ...] = ()
    doorstop_hierarchies: tuple[DoorstopHierarchyDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> StandardCatalog:
        domains = {item.key for item in self.knowledge_domains}
        sectors = {item.key for item in self.industry_sectors}
        families = {item.key for item in self.families}
        if len(families) != len(self.families):
            raise ValueError("family keys must be unique")
        document_keys = set(families)
        for family in self.families:
            document_keys.update(part.key for part in family.parts)
            document_keys.update(
                supplement.key for part in family.parts for supplement in part.supplements
            )
        expected_count = len(self.families) + sum(
            len(family.parts) + sum(len(part.supplements) for part in family.parts)
            for family in self.families
        )
        if len(document_keys) != expected_count:
            raise ValueError("family, part and supplement keys must be globally unique")
        for family in self.families:
            unknown_domains = set(family.classification.knowledge_domains) - domains
            unknown_sectors = set(family.classification.industry_sectors) - sectors
            if unknown_domains or unknown_sectors:
                raise ValueError(
                    f"unknown classification on {family.key}: {unknown_domains | unknown_sectors}"
                )
            relations = list(family.relations)
            for part in family.parts:
                for supplement in part.supplements:
                    relations.extend(supplement.relations)
                    if not any(
                        relation.type == RelationType.SUPPLEMENTS and relation.target == part.key
                        for relation in supplement.relations
                    ):
                        raise ValueError(
                            f"supplement {supplement.key} must declare supplements -> {part.key}"
                        )
            for relation in relations:
                if relation.target not in document_keys:
                    raise ValueError(f"unknown relation target {relation.target!r} on {family.key}")
        for profile in self.profiles:
            unknown = set(profile.families) - families
            if unknown:
                raise ValueError(f"unknown profile families on {profile.key}: {unknown}")
        lineage_keys = {lineage.key for lineage in self.lineages}
        if len(lineage_keys) != len(self.lineages):
            raise ValueError("lineage keys must be unique")
        for lineage in self.lineages:
            unknown_members = set(lineage.members) - document_keys
            unknown_domains = set(lineage.knowledge_domains) - domains
            unknown_sectors = set(lineage.industry_sectors) - sectors
            if unknown_members:
                raise ValueError(f"unknown lineage members on {lineage.key}: {unknown_members}")
            if unknown_domains or unknown_sectors:
                raise ValueError(
                    f"unknown lineage classification on {lineage.key}: "
                    f"{unknown_domains | unknown_sectors}"
                )
        hierarchy_keys = {item.key for item in self.doorstop_hierarchies}
        if len(hierarchy_keys) != len(self.doorstop_hierarchies):
            raise ValueError("doorstop hierarchy keys must be unique")
        for hierarchy in self.doorstop_hierarchies:
            unknown = set(hierarchy.families) - families
            if unknown:
                raise ValueError(
                    f"unknown families on doorstop hierarchy {hierarchy.key}: {unknown}"
                )
        return self

    def family(self, key: str) -> StandardFamilyDefinition:
        for family in self.families:
            if family.key == key:
                return family
        raise KeyError(key)

    def profile(self, key: str) -> StandardProfile:
        for profile in self.profiles:
            if profile.key == key:
                return profile
        raise KeyError(key)

    def doorstop_hierarchy(self, key: str) -> DoorstopHierarchyDefinition:
        for hierarchy in self.doorstop_hierarchies:
            if hierarchy.key == key:
                return hierarchy
        raise KeyError(key)
