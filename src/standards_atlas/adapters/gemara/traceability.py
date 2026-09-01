"""Deterministic Standards Atlas ↔ Gemara traceability projection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.adapters.gemara.mapper import _external_version, gemara_id
from standards_atlas.adapters.gemara.models import GemaraGuidanceCatalog
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import RelationScope


class GemaraTraceabilityEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    gemara_entry_id: str = Field(min_length=1)
    entry_type: Literal["guideline", "statement"]
    owner_guideline_id: str = Field(min_length=1)


class GemaraTraceabilityRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_clause_id: str = Field(min_length=1)
    source_gemara_entry_id: str | None = None
    source_owner_guideline_id: str | None = None
    kind: str = Field(min_length=1)
    scope: Literal["internal", "external"]
    target_reference: str = Field(min_length=1)
    target_document_key: str | None = None
    target_clause_id: str | None = None
    target_gemara_entry_id: str | None = None
    target_owner_guideline_id: str | None = None
    mapping_reference_id: str | None = None
    represented_as: Literal["see-also", "mapping-reference", "traceability-only"]
    display_text: str | None = None
    rationale: str | None = None


class GemaraTraceabilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    document_key: str = Field(min_length=1)
    gemara_catalog_id: str = Field(min_length=1)
    exported_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[GemaraTraceabilityEntry, ...] = ()
    relations: tuple[GemaraTraceabilityRelation, ...] = ()


def build_traceability(
    document: PublicationDocument,
    catalog: GemaraGuidanceCatalog,
    *,
    exported_artifact_sha256: str,
) -> GemaraTraceabilityManifest:
    """Build precise clause/entry provenance for one Gemara export."""
    entry_by_clause: dict[str, GemaraTraceabilityEntry] = {}
    owner_by_clause: dict[str, str] = {}

    clause_ids = {clause.id.value for clause in document.clauses}
    normalized_clause_ids = {gemara_id(value): value for value in clause_ids}
    for guideline in catalog.guidelines or ():
        original = normalized_clause_ids.get(guideline.id)
        if original is not None:
            entry_by_clause[original] = GemaraTraceabilityEntry(
                clause_id=original,
                gemara_entry_id=guideline.id,
                entry_type="guideline",
                owner_guideline_id=guideline.id,
            )
            owner_by_clause[original] = guideline.id
        for statement in guideline.statements or ():
            original = normalized_clause_ids.get(statement.id)
            if original is None:
                continue
            entry_by_clause[original] = GemaraTraceabilityEntry(
                clause_id=original,
                gemara_entry_id=statement.id,
                entry_type="statement",
                owner_guideline_id=guideline.id,
            )
            owner_by_clause[original] = guideline.id

    relations: list[GemaraTraceabilityRelation] = []
    for clause in document.clauses:
        source_entry = entry_by_clause.get(clause.id.value)
        for relation in clause.reference_relations:
            target_entry = (
                entry_by_clause.get(relation.target_clause_id)
                if relation.target_clause_id is not None
                else None
            )
            mapping_reference_id = None
            represented_as: Literal["see-also", "mapping-reference", "traceability-only"]
            if relation.scope is RelationScope.INTERNAL:
                source_owner = owner_by_clause.get(clause.id.value)
                target_owner = (
                    owner_by_clause.get(relation.target_clause_id)
                    if relation.target_clause_id is not None
                    else None
                )
                represented_as = (
                    "see-also"
                    if source_owner is not None
                    and target_owner is not None
                    and source_owner != target_owner
                    else "traceability-only"
                )
            else:
                version = _external_version(relation.display_text)
                if relation.target_document_key and version:
                    mapping_reference_id = gemara_id(
                        f"ref-{relation.target_document_key}-{version}"
                    )
                    represented_as = "mapping-reference"
                else:
                    represented_as = "traceability-only"

            relations.append(
                GemaraTraceabilityRelation(
                    source_clause_id=clause.id.value,
                    source_gemara_entry_id=(source_entry.gemara_entry_id if source_entry else None),
                    source_owner_guideline_id=(
                        source_entry.owner_guideline_id if source_entry else None
                    ),
                    kind=relation.kind.value,
                    scope=relation.scope.value,
                    target_reference=relation.target_reference,
                    target_document_key=relation.target_document_key,
                    target_clause_id=relation.target_clause_id,
                    target_gemara_entry_id=(target_entry.gemara_entry_id if target_entry else None),
                    target_owner_guideline_id=(
                        target_entry.owner_guideline_id if target_entry else None
                    ),
                    mapping_reference_id=mapping_reference_id,
                    represented_as=represented_as,
                    display_text=relation.display_text,
                    rationale=relation.rationale,
                )
            )

    return GemaraTraceabilityManifest(
        document_key=document.key.value,
        gemara_catalog_id=catalog.metadata.id,
        exported_artifact_sha256=exported_artifact_sha256,
        entries=tuple(entry_by_clause[key] for key in sorted(entry_by_clause)),
        relations=tuple(relations),
    )
