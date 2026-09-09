"""Inventory of interfaces whose versions cross architectural lifecycle boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleBoundary(StrEnum):
    """Boundary that makes an interface independently consumable."""

    PERSISTENCE = "persistence"
    PROCESS = "process"
    PACKAGED_RESOURCE = "packaged-resource"
    PUBLIC_CONTRACT = "public-contract"


class VersionAxis(StrEnum):
    """Independent version axes carried by an interface."""

    SCHEMA = "schema"
    RESOURCE = "resource"


@dataclass(frozen=True)
class VersionedInterface:
    """One explicit lifecycle-crossing interface and its versioning obligations."""

    id: str
    location: str
    boundary: LifecycleBoundary
    axes: tuple[VersionAxis, ...]
    schema_family: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError(f"versioned interface {self.id!r} must declare at least one axis")
        if VersionAxis.SCHEMA in self.axes and self.schema_family is None:
            raise ValueError(
                f"versioned interface {self.id!r} declares schema versioning "
                "without a schema family"
            )
        if VersionAxis.SCHEMA not in self.axes and self.schema_family is not None:
            raise ValueError(
                f"versioned interface {self.id!r} has a schema family but no schema version axis"
            )


VERSIONED_INTERFACES: tuple[VersionedInterface, ...] = (
    VersionedInterface(
        "qualification-consensus", "**/consensus-report.json", LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,), "qualification-consensus",
        "Measured process primary/set; legacy 4.0 preserves policy fingerprints.",
    ),
    VersionedInterface(
        "golden-corpus-proposal", "**/golden-corpus-proposal.yaml", LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,), "golden-corpus-proposal",
        "Review proposal including explicit process availability and support.",
    ),
    VersionedInterface(
        "cbox-enrichments",
        "clause-descriptor.enrichment_context",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "cbox-enrichments",
        "Read-only canonical attribute projection.",
    ),
    VersionedInterface(
        "cbox-report",
        "local/**/cbox*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "cbox-report",
        "Local effective post-import CBox and provenance.",
    ),
    VersionedInterface(
        "atlasdata-enrichments",
        "data/enrichments/*.yaml",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "atlasdata-enrichments",
        "Selected generated/confirmed attributes; protected values are hash references.",
    ),
    VersionedInterface(
        "knowledge-evidence",
        ".atlas/data/knowledge-evidence/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-evidence",
        "Private immutable hydration payloads.",
    ),
    VersionedInterface(
        "atlasdata-knowledge-report",
        "local/**/atlasdata-knowledge*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "atlasdata-knowledge-report",
        "Explicit export/import preflight reports.",
    ),
    VersionedInterface(
        "knowledge-adoption-batch",
        "local/**/knowledge-adoption-batch.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-adoption-batch",
        "Optional serialized partial-update contract; omitted fields remain unaddressed.",
    ),
    VersionedInterface(
        "knowledge-adoption-report",
        "local/**/knowledge-adoption-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-adoption-report",
        "Explicit canonical adoption preview/write report, not public AtlasData.",
    ),
    VersionedInterface(
        "engineering-document",
        ".atlas/data/documents/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "engineering-document",
        "Canonical persisted knowledge state for one physical document.",
    ),
    VersionedInterface(
        "standards-manifest",
        "manifests/standards*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "standards-manifest",
        "Authored workflow/catalog input consumed independently of Python code.",
    ),
    VersionedInterface(
        "qualification-matrix-manifest",
        "manifests/*qualification*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "qualification-matrix-manifest",
        "Authored qualification execution contract.",
    ),
    VersionedInterface(
        "semantic-task",
        "resources/semantic/tasks/<id>/<version>/task.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "semantic-task-resource",
        "Task resource version identifies inference semantics independently of YAML schema.",
    ),
    VersionedInterface(
        "semantic-profile",
        "resources/semantic/profiles/<id>/<version>/profile.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "semantic-profile-resource",
        "Profile version identifies a domain composition independently of YAML schema.",
    ),
    VersionedInterface(
        "semantic-ontology",
        "resources/ontologies/<id>/<version>/ontology.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "ontology-resource",
        "Vocabulary/resource version identifies controlled meaning independently of YAML schema.",
    ),
    VersionedInterface(
        "structural-taxonomy",
        "resources/structure-taxonomies/<id>/<version>/taxonomy.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "structural-taxonomy-resource",
        "Taxonomy definition version evolves independently of its serialization schema.",
    ),
    VersionedInterface(
        "formal-ontology",
        "resources/formal_ontologies/<id>/<version>/ontology.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "formal-ontology-resource",
        "OWL/TBox resource identity is independent of the ontology-definition schema.",
    ),
    VersionedInterface(
        "semantic-prompt",
        "resources/semantic/prompts/<task>/<version>/",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.RESOURCE,),
        notes=(
            "Prompt versions are independently selectable inference inputs; "
            "their output schema is task-owned."
        ),
    ),
    VersionedInterface(
        "formal-semantic-projection",
        ".atlas/data/formal-semantic-projections/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "formal-semantic-projection",
        "Persisted projection records referenced ontology/resource identity separately.",
    ),
    VersionedInterface(
        "semantic-extraction",
        ".atlas/data/semantic-extractions/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "semantic-extraction",
        (
            "Persisted extraction carries task/prompt/model provenance independently "
            "of schema version."
        ),
    ),
)


def schema_managed_interfaces() -> tuple[VersionedInterface, ...]:
    """Return interfaces whose serialization contract is centrally schema-managed."""

    return tuple(item for item in VERSIONED_INTERFACES if VersionAxis.SCHEMA in item.axes)
