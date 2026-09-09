"""Versioned, text-safe AtlasData transport, not a second canonical model.

Values are validated against canonical field types. Context objects containing
source text travel by content-addressed reference with a bounded public view.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from standards_atlas.domain.model.context_routing import ScopeReach
from standards_atlas.domain.model.enrichment_patch import SemanticEnrichmentPatch
from standards_atlas.domain.model.identifiers import StandardReference
from standards_atlas.domain.model.knowledge_state import ConfirmedAttribute, GeneratedAttribute

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
LegacyMd5 = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
SafeKey = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
AttributePath = Literal[
    "enrichments.semantic.primary_function",
    "enrichments.semantic.primary_knowledge_kind",
    "enrichments.semantic.primary_process_function",
    "enrichments.semantic.statement_functions",
    "enrichments.semantic.knowledge_kinds",
    "enrichments.semantic.process_functions",
    "enrichments.semantic.applicability_present",
    "enrichments.semantic.applicability_functions",
    "enrichments.semantic.role_semantics_present",
    "enrichments.semantic.role_relation_types",
    "enrichments.semantic.role_relations",
    "enrichments.subject_context",
    "enrichments.context_routing",
]

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "statement_functions": ("primary_function", "statement_functions"),
    "knowledge_kinds": ("primary_knowledge_kind", "knowledge_kinds"),
    "process_functions": ("primary_process_function", "process_functions"),
    "applicability": ("applicability_present", "applicability_functions"),
    "role_semantics": ("role_semantics_present", "role_relation_types", "role_relations"),
}
DIMENSION_PATHS = {
    name: tuple(f"enrichments.semantic.{field}" for field in fields)
    for name, fields in DIMENSIONS.items()
}
DIMENSION_PATHS.update(
    {
        "subject_context": ("enrichments.subject_context",),
        "context_routing": ("enrichments.context_routing",),
    }
)
ALL_PATHS = tuple(path for paths in DIMENSION_PATHS.values() for path in paths)
SEMANTIC_ADAPTERS = {
    name: TypeAdapter(field.annotation)
    for name, field in SemanticEnrichmentPatch.model_fields.items()
}
PRIVATE_PATHS = {
    "enrichments.subject_context",
    "enrichments.context_routing",
    "enrichments.semantic.role_relations",
}


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SubjectView(_Strict):
    # Controlled use of authored semantic labels, never evidence/source sentences.
    normalized_label: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    ambiguous_candidates: tuple[str, ...] = ()


class ScopeView(_Strict):
    source_clause_id: str
    reaches: tuple[ScopeReach, ...]
    conditions: int = Field(ge=0)
    exclusions: int = Field(ge=0)
    qualifications: int = Field(ge=0)


class ReferenceView(_Strict):
    source_clause_id: str
    document_key: str | None = None
    clause_id: str | None = None
    reference: str
    role: Literal[
        "defines",
        "constrains",
        "requires",
        "provides_procedure",
        "provides_exception",
        "provides_applicability",
        "provides_evidence",
        "refines",
        "depends_on",
        "other",
    ]


class RoutingView(_Strict):
    scopes: tuple[ScopeView, ...] = ()
    references: tuple[ReferenceView, ...] = ()


class RoleView(_Strict):
    count: int = Field(ge=0)


class PublishedAttribute(_Strict):
    path: AttributePath
    origin: Literal["generated", "confirmed", "unattributed"]
    availability: Literal["known", "unknown"] = "known"
    value: JsonValue = None
    generated: GeneratedAttribute | None = None
    confirmed: ConfirmedAttribute | None = None
    private_value_sha256: Digest | None = None
    private_provenance_sha256: Digest | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> PublishedAttribute:
        if self.origin == "generated":
            if self.generated is None or self.confirmed is not None:
                raise ValueError("generated attributes require only generated provenance")
            if self.generated.path != self.path or self.generated.availability != self.availability:
                raise ValueError("generated provenance must match attribute path and availability")
        elif self.origin == "confirmed":
            if self.confirmed is None or self.generated is not None:
                raise ValueError("confirmed attributes require only confirmed provenance")
            if self.confirmed.path != self.path or self.availability != "known":
                raise ValueError("confirmed provenance must match a known attribute")
        elif (
            self.generated is not None or self.confirmed is not None or self.availability != "known"
        ):
            raise ValueError("unattributed values must be known without invented provenance")
        if self.origin == "unattributed" and self.private_provenance_sha256 is not None:
            raise ValueError("unattributed values cannot reference invented provenance")
        if self.availability == "unknown":
            if self.value is not None or self.private_value_sha256 is not None:
                raise ValueError("unknown attribute cannot carry a value")
            return self
        if self.path in PRIVATE_PATHS:
            if self.private_value_sha256 is None:
                raise ValueError("context and exact role values require a private value reference")
            models = {
                "enrichments.subject_context": SubjectView,
                "enrichments.context_routing": RoutingView,
                "enrichments.semantic.role_relations": RoleView,
            }
            models[self.path].model_validate(self.value)
        else:
            if self.private_value_sha256 is not None:
                raise ValueError("categorical values cannot use a private value reference")
            field = self.path.rsplit(".", 1)[-1]
            # Validate in JSON mode: arrays are tuples, but bool/int coercions are forbidden.
            SEMANTIC_ADAPTERS[field].validate_json(json.dumps(self.value), strict=True)
        return self


class ClauseKnowledge(_Strict):
    clause_id: str = Field(min_length=1)
    atlasdata_md5: LegacyMd5
    reference: StandardReference
    heading: str | None = None
    heading_sha256: Digest
    atlasdata_heading_sha256: Digest
    content_sha256: Digest | None = None
    attributes: tuple[PublishedAttribute, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_paths(self) -> ClauseKnowledge:
        paths = [item.path for item in self.attributes]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate attribute paths in AtlasData clause")
        return self


class AtlasDataKnowledge(_Strict):
    manifest_type: Literal["atlasdata-enrichments"] = "atlasdata-enrichments"
    schema_version: Literal["1.1"] = "1.1"
    document_key: SafeKey
    family_key: SafeKey
    atlasdata_file: str = Field(min_length=1)
    selection_part: str | None = None
    publication_year: int | None = None  # Manifest edition, not inferred from a legacy family year.
    structure_sha256: Digest
    clauses: tuple[ClauseKnowledge, ...] = ()

    @model_validator(mode="after")
    def unique_clauses(self) -> AtlasDataKnowledge:
        ids = [item.clause_id for item in self.clauses]
        refs = [item.reference.as_text() for item in self.clauses]
        if len(ids) != len(set(ids)) or len(refs) != len(set(refs)):
            raise ValueError("duplicate clause identity in AtlasData enrichments")
        return self


class EvidenceBlob(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["value", "generated", "confirmed"]
    path: AttributePath
    value: JsonValue


class TransferChange(_Strict):
    document_key: str
    clause_id: str
    path: str
    status: str
    before: JsonValue = None
    after: JsonValue = None
    reason: str | None = None


class AtlasDataKnowledgeReport(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["export", "import"]
    write_requested: bool
    document_keys: tuple[str, ...]
    changed_targets: tuple[str, ...]
    written_targets: tuple[str, ...]
    status_counts: dict[str, int]
    content_verified_clauses: int = 0
    content_unverified_clauses: int = 0
    changes: tuple[TransferChange, ...] = ()
