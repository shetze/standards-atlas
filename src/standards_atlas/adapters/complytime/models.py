"""Models for deterministic ComplyTime governance source bundles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GovernanceBundleArtifact(BaseModel):
    """One immutable artifact referenced by a governance bundle manifest."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    path: str = Field(min_length=1)
    media_type: str = Field(alias="media-type", min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_id: str | None = Field(default=None, alias="catalog-id")


class GovernanceBundleSource(BaseModel):
    """Source standard represented by the bundle."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    document_key: str = Field(alias="document-key", min_length=1)
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)


class GovernanceBundleManifest(BaseModel):
    """Machine-readable hand-off contract for downstream ComplyTime authoring."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: str = Field(default="1.0", alias="schema-version")
    bundle_id: str = Field(alias="bundle-id", min_length=1)
    source: GovernanceBundleSource
    gemara_version: str = Field(alias="gemara-version", min_length=1)
    guidance: GovernanceBundleArtifact
    controls: GovernanceBundleArtifact
    traceability: GovernanceBundleArtifact


class GovernanceBundleTraceability(BaseModel):
    """Consolidated traceability for the GuidanceCatalog and ControlCatalog."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    document_key: str = Field(min_length=1)
    guidance: dict[str, object]
    controls: dict[str, object]
