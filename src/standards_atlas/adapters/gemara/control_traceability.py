"""Traceability sidecar for Gemara ControlCatalog exports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.adapters.gemara.contract import gemara_id, guidance_catalog_id
from standards_atlas.adapters.gemara.models import GemaraControlCatalog
from standards_atlas.application.model import PublicationDocument


class GemaraControlTraceabilityEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    gemara_entry_id: str = Field(min_length=1)
    entry_type: Literal["control", "assessment_requirement"]
    owner_control_id: str = Field(min_length=1)
    guidance_catalog_id: str = Field(min_length=1)
    guidance_entry_id: str = Field(min_length=1)


class GemaraControlTraceabilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    document_key: str = Field(min_length=1)
    gemara_catalog_id: str = Field(min_length=1)
    guidance_catalog_id: str = Field(min_length=1)
    exported_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[GemaraControlTraceabilityEntry, ...] = ()


def build_control_traceability(
    document: PublicationDocument,
    catalog: GemaraControlCatalog,
    *,
    exported_artifact_sha256: str,
) -> GemaraControlTraceabilityManifest:
    """Bind controls and assessment requirements to canonical clause ids."""
    original_by_normalized = {
        gemara_id(clause.id.value): clause.id.value for clause in document.clauses
    }
    entries: list[GemaraControlTraceabilityEntry] = []

    for control in catalog.controls or ():
        guidance_entry_id = _control_guidance_entry_id(control)
        if guidance_entry_id is None:
            raise ValueError(f"Control {control.id!r} has no Layer-1 guidance mapping.")
        control_clause_id = _control_clause_id(control.id, original_by_normalized)
        if control_clause_id is not None:
            entries.append(
                GemaraControlTraceabilityEntry(
                    clause_id=control_clause_id,
                    gemara_entry_id=control.id,
                    entry_type="control",
                    owner_control_id=control.id,
                    guidance_catalog_id=guidance_catalog_id(document.key.value),
                    guidance_entry_id=guidance_entry_id,
                )
            )

        for requirement in control.assessment_requirements:
            normalized = _strip_prefix(requirement.id, "ar-")
            clause_id = original_by_normalized.get(normalized)
            if clause_id is None:
                continue
            entries.append(
                GemaraControlTraceabilityEntry(
                    clause_id=clause_id,
                    gemara_entry_id=requirement.id,
                    entry_type="assessment_requirement",
                    owner_control_id=control.id,
                    guidance_catalog_id=guidance_catalog_id(document.key.value),
                    guidance_entry_id=guidance_entry_id,
                )
            )

    return GemaraControlTraceabilityManifest(
        document_key=document.key.value,
        gemara_catalog_id=catalog.metadata.id,
        guidance_catalog_id=guidance_catalog_id(document.key.value),
        exported_artifact_sha256=exported_artifact_sha256,
        entries=tuple(
            sorted(
                entries,
                key=lambda item: (
                    item.clause_id,
                    item.entry_type,
                    item.gemara_entry_id,
                ),
            )
        ),
    )


def _control_guidance_entry_id(control: object) -> str | None:
    mappings = getattr(control, "guidelines", None) or ()
    if not mappings:
        return None
    entries = mappings[0].entries
    return entries[0].reference_id if entries else None


def _control_clause_id(
    control_id: str,
    original_by_normalized: dict[str, str],
) -> str | None:
    direct = original_by_normalized.get(control_id)
    if direct is not None:
        return direct
    return original_by_normalized.get(_strip_prefix(control_id, "control-"))


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix) :] if value.startswith(prefix) else value
