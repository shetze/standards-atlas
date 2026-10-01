"""Deterministic source/input binding for AP02 structured-context extraction.

This module binds four deliberately separate facts: the source state, the reachable candidate
space, the selection decision, and the exact input surfaces that a later renderer may supply to a
model.  Proposal/knowledge/report data are intentionally absent from every fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.context.context_selection import (
    ContextReachHint,
    ContextSelectionEntry,
    ContextSelectionReason,
    StructuredContextSelection,
)
from standards_atlas.application.context.source_surfaces import (
    SourceDocumentBinding,
    SourceMediaHandle,
    SourceSurfaceAvailability,
    SourceSurfaceIdentity,
    SourceSurfaceOrigin,
    SourceSurfaceRef,
    source_document_binding,
)
from standards_atlas.application.context.structured_candidates import (
    ContextCandidatePath,
    ContextCandidateReason,
    StructuredContextCandidates,
)
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import EngineeringDocument

CONTEXT_SOURCE_PACKAGE_CONTRACT = "source-bound-context-input-v1"
CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT = "source-bound-context-binding-v1"
CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION = 1
_SOURCE_STATE_CONTRACT = "source-bound-context-source-state-v1"
_CANDIDATE_SPACE_CONTRACT = "source-bound-context-candidate-space-v1"
_SELECTION_DECISION_CONTRACT = "source-bound-context-selection-decision-v1"
_ACTUAL_INPUT_CONTRACT = "source-bound-context-actual-input-v1"


class ContextReuseReason(StrEnum):
    """Deterministic reason why a previously bound input may not be reused."""

    CONTRACT_CHANGED = "contract_changed"
    SOURCE_STATE_CHANGED = "source_state_changed"
    CANDIDATE_SPACE_CHANGED = "candidate_space_changed"
    SELECTION_CHANGED = "selection_changed"
    ACTUAL_INPUT_CHANGED = "actual_input_changed"


class ContextInputFingerprints(BaseModel):
    """Independent fingerprints of the four AP02 input-binding dimensions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_state_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_space_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_decision_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    actual_input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class BoundContextInputSurface(BaseModel):
    """One exact surface/excerpt that is actually available to the later renderer.

    ``text`` is private source material.  ``start_offset``/``end_offset`` are absolute Python
    character offsets in the canonical decoded surface, even when only an excerpt is supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_source_ref: str = Field(min_length=1)
    source_ref: SourceSurfaceRef
    identity: SourceSurfaceIdentity
    origin: SourceSurfaceOrigin
    origin_reference: str | None = None
    source_backed: bool
    rendering_id: str = Field(min_length=1)
    surface_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    text: str
    media: SourceMediaHandle | None = None
    candidate_reasons: tuple[ContextCandidateReason, ...] = Field(min_length=1)
    structural_paths: tuple[ContextCandidatePath, ...] = Field(min_length=1)
    selection_reason: ContextSelectionReason
    reach_hints: tuple[ContextReachHint, ...] = Field(min_length=1)
    semantic_reach_confirmed: Literal[False] = False

    @model_validator(mode="after")
    def exact_excerpt_is_self_consistent(self) -> BoundContextInputSurface:
        if self.end_offset <= self.start_offset:
            raise ValueError("bound input surface offsets must form a non-empty range")
        if self.end_offset - self.start_offset != len(self.text):
            raise ValueError("bound input surface offsets must match the delivered excerpt length")
        actual = _sha256_text(self.text)
        if actual != self.content_sha256:
            raise ValueError("bound input surface content hash does not match delivered text")
        if self.source_ref.document_key != self.identity.document.document_key:
            raise ValueError("bound input surface document identity does not match source ref")
        if self.source_ref.clause_id != self.identity.clause_id:
            raise ValueError("bound input surface clause identity does not match source ref")
        if self.source_ref.source_kind != self.identity.source_kind:
            raise ValueError("bound input surface source kind does not match resolved identity")
        if self.source_ref.media_kind != self.identity.media_kind:
            raise ValueError("bound input surface media kind does not match resolved identity")
        if self.source_ref.block_id != self.identity.block_id:
            raise ValueError("bound input surface block identity does not match resolved identity")
        return self


class ContextSourcePackage(SchemaBoundModel):
    """Private, reconstructable source package for one future extraction input.

    The package may contain protected source text and must therefore not be used as a public
    lineage record.  :class:`ContextSourcePackageBinding` is the text-free public counterpart.
    """

    SCHEMA_FAMILY: ClassVar[str] = "context-source-package"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION
    contract_id: Literal["source-bound-context-input-v1"] = CONTEXT_SOURCE_PACKAGE_CONTRACT
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    primary_document: SourceDocumentBinding
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    fingerprints: ContextInputFingerprints
    candidate_inventory: StructuredContextCandidates
    selection: StructuredContextSelection
    input_surfaces: tuple[BoundContextInputSurface, ...] = ()

    @model_validator(mode="after")
    def package_contract_is_consistent(self) -> ContextSourcePackage:
        if self.primary_document.document_key != self.document_key:
            raise ValueError("source package primary document key differs from package")
        if self.primary_document.source_revision != self.document_revision:
            raise ValueError("source package primary document revision differs from package")
        if self.document_key != self.candidate_inventory.document_key:
            raise ValueError("source package document key differs from candidate inventory")
        if self.document_key != self.selection.document_key:
            raise ValueError("source package document key differs from selection")
        if self.document_revision != self.candidate_inventory.document_revision:
            raise ValueError("source package revision differs from candidate inventory")
        if self.document_revision != self.selection.document_revision:
            raise ValueError("source package revision differs from selection")
        if self.target_clause_id != self.candidate_inventory.target_clause_id:
            raise ValueError("source package target differs from candidate inventory")
        if self.target_clause_id != self.selection.target_clause_id:
            raise ValueError("source package target differs from selection")
        refs = [surface.package_source_ref for surface in self.input_surfaces]
        if len(refs) != len(set(refs)):
            raise ValueError("source package input surface refs must be unique")
        expected = ContextInputFingerprints(
            source_state_sha256=_source_state_fingerprint(
                self.primary_document.model_dump(mode="json"), self.candidate_inventory
            ),
            candidate_space_sha256=_candidate_space_fingerprint(self.candidate_inventory),
            selection_decision_sha256=_selection_decision_fingerprint(self.selection),
            actual_input_sha256=_actual_input_fingerprint(
                document_key=self.document_key,
                document_revision=self.document_revision,
                target_clause_id=self.target_clause_id,
                target_reference=self.target_reference,
                surfaces=self.input_surfaces,
            ),
        )
        if self.fingerprints != expected:
            raise ValueError("source package fingerprints do not match bound package content")
        return self


class ContextSourcePackageBinding(BaseModel):
    """Text-free immutable reference to a privately persisted source package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["source-bound-context-binding-v1"] = (
        CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT
    )
    package_schema_version: Literal[1] = CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION
    package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    fingerprints: ContextInputFingerprints


class ContextReuseCheck(BaseModel):
    """Pure compatibility result; no source retrieval and no semantic approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reusable: bool
    reasons: tuple[ContextReuseReason, ...] = ()
    previous: ContextInputFingerprints
    current: ContextInputFingerprints


def build_context_source_package(
    document: EngineeringDocument,
    inventory: StructuredContextCandidates,
    selection: StructuredContextSelection,
) -> ContextSourcePackage:
    """Bind one deterministic Series-B inventory/selection to exact private input surfaces."""

    binding = source_document_binding(document)
    _validate_package_inputs(binding.source_revision, inventory, selection)

    input_surfaces = tuple(_bound_input_surface(entry) for entry in selection.selected)
    source_state_sha256 = _source_state_fingerprint(binding.model_dump(mode="json"), inventory)
    candidate_space_sha256 = _candidate_space_fingerprint(inventory)
    selection_decision_sha256 = _selection_decision_fingerprint(selection)
    actual_input_sha256 = _actual_input_fingerprint(
        document_key=selection.document_key,
        document_revision=selection.document_revision,
        target_clause_id=selection.target_clause_id,
        target_reference=selection.target_reference,
        surfaces=input_surfaces,
    )
    return ContextSourcePackage(
        document_key=selection.document_key,
        document_revision=selection.document_revision,
        primary_document=binding,
        target_clause_id=selection.target_clause_id,
        target_reference=selection.target_reference,
        fingerprints=ContextInputFingerprints(
            source_state_sha256=source_state_sha256,
            candidate_space_sha256=candidate_space_sha256,
            selection_decision_sha256=selection_decision_sha256,
            actual_input_sha256=actual_input_sha256,
        ),
        candidate_inventory=inventory,
        selection=selection,
        input_surfaces=input_surfaces,
    )


def check_context_source_package_reuse(
    previous: ContextSourcePackageBinding,
    current: ContextSourcePackage,
) -> ContextReuseCheck:
    """Return whether a previous private package binding is safe to reuse for ``current``."""

    reasons: list[ContextReuseReason] = []
    if (
        previous.contract_id != CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT
        or previous.package_schema_version != CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION
    ):
        reasons.append(ContextReuseReason.CONTRACT_CHANGED)
    if previous.fingerprints.source_state_sha256 != current.fingerprints.source_state_sha256:
        reasons.append(ContextReuseReason.SOURCE_STATE_CHANGED)
    if previous.fingerprints.candidate_space_sha256 != current.fingerprints.candidate_space_sha256:
        reasons.append(ContextReuseReason.CANDIDATE_SPACE_CHANGED)
    if (
        previous.fingerprints.selection_decision_sha256
        != current.fingerprints.selection_decision_sha256
    ):
        reasons.append(ContextReuseReason.SELECTION_CHANGED)
    if previous.fingerprints.actual_input_sha256 != current.fingerprints.actual_input_sha256:
        reasons.append(ContextReuseReason.ACTUAL_INPUT_CHANGED)
    return ContextReuseCheck(
        reusable=not reasons,
        reasons=tuple(reasons),
        previous=previous.fingerprints,
        current=current.fingerprints,
    )


def context_source_package_content_sha256(package: ContextSourcePackage) -> str:
    """Hash the canonical persisted bytes without claiming that those bytes are available."""

    encoded = (
        json.dumps(
            package.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def context_source_package_binding(
    package: ContextSourcePackage,
    *,
    package_sha256: str | None = None,
) -> ContextSourcePackageBinding:
    """Build a text-free binding; persistence must still be established by the caller/repository."""

    return ContextSourcePackageBinding(
        package_sha256=package_sha256 or context_source_package_content_sha256(package),
        document_key=package.document_key,
        document_revision=package.document_revision,
        target_clause_id=package.target_clause_id,
        target_reference=package.target_reference,
        fingerprints=package.fingerprints,
    )


def _validate_package_inputs(
    document_revision: str,
    inventory: StructuredContextCandidates,
    selection: StructuredContextSelection,
) -> None:
    if inventory.document_revision != document_revision:
        raise ValueError("candidate inventory does not belong to the supplied document revision")
    if selection.document_revision != document_revision:
        raise ValueError("selection does not belong to the supplied document revision")
    if selection.candidate_contract_id != inventory.contract_id:
        raise ValueError("selection candidate contract differs from supplied inventory")
    if selection.document_key != inventory.document_key:
        raise ValueError("selection document differs from supplied inventory")
    if selection.target_clause_id != inventory.target_clause_id:
        raise ValueError("selection target differs from supplied inventory")
    inventory_by_id = {candidate.candidate_id: candidate for candidate in inventory.candidates}
    for entry in (*selection.selected, *selection.omitted):
        candidate = inventory_by_id.get(entry.candidate.candidate_id)
        if candidate is None or candidate != entry.candidate:
            raise ValueError("selection contains a candidate outside the supplied inventory")


def _bound_input_surface(entry: ContextSelectionEntry) -> BoundContextInputSurface:
    resolution = entry.candidate.resolution
    if resolution.availability is not SourceSurfaceAvailability.AVAILABLE:
        raise ValueError("selected context input surface is not available")
    if resolution.identity is None or resolution.text is None:
        raise ValueError("selected context input surface lacks resolvable private text")
    if (
        resolution.rendering_id is None
        or resolution.surface_sha256 is None
        or resolution.content_sha256 is None
        or resolution.start_offset is None
        or resolution.end_offset is None
    ):
        raise ValueError("selected context input surface lacks canonical rendering metadata")
    return BoundContextInputSurface(
        package_source_ref=entry.candidate.candidate_id,
        source_ref=entry.candidate.source_ref,
        identity=resolution.identity,
        origin=resolution.origin,
        origin_reference=resolution.origin_reference,
        source_backed=resolution.source_backed,
        rendering_id=resolution.rendering_id,
        surface_sha256=resolution.surface_sha256,
        content_sha256=resolution.content_sha256,
        start_offset=resolution.start_offset,
        end_offset=resolution.end_offset,
        text=resolution.text,
        media=resolution.media,
        candidate_reasons=entry.candidate.reasons,
        structural_paths=entry.candidate.paths,
        selection_reason=entry.selection_reason,
        reach_hints=entry.reach_hints,
        semantic_reach_confirmed=entry.semantic_reach_confirmed,
    )


def _source_state_fingerprint(
    primary_document_binding: dict[str, object], inventory: StructuredContextCandidates
) -> str:
    surfaces = []
    for candidate in inventory.candidates:
        resolution = candidate.resolution
        surfaces.append(
            {
                "source_ref": candidate.source_ref.model_dump(mode="json"),
                "availability": resolution.availability.value,
                "identity": (
                    resolution.identity.model_dump(mode="json")
                    if resolution.identity is not None
                    else None
                ),
                "origin": resolution.origin.value,
                "origin_reference": resolution.origin_reference,
                "source_backed": resolution.source_backed,
                "rendering_id": resolution.rendering_id,
                "surface_sha256": resolution.surface_sha256,
                "content_sha256": resolution.content_sha256,
                "start_offset": resolution.start_offset,
                "end_offset": resolution.end_offset,
                "media": resolution.media.model_dump(mode="json") if resolution.media else None,
            }
        )
    return _canonical_sha256(
        {
            "contract": _SOURCE_STATE_CONTRACT,
            "primary_document": primary_document_binding,
            "surfaces": surfaces,
        }
    )


def _candidate_space_fingerprint(inventory: StructuredContextCandidates) -> str:
    return _canonical_sha256(
        {
            "contract": _CANDIDATE_SPACE_CONTRACT,
            "candidate_contract_id": inventory.contract_id,
            "document_key": inventory.document_key,
            "document_revision": inventory.document_revision,
            "target_clause_id": inventory.target_clause_id,
            "target_reference": inventory.target_reference,
            "ancestor_path": [item.model_dump(mode="json") for item in inventory.ancestor_path],
            "sequence_clause_ids": list(inventory.sequence_clause_ids),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "source_ref": candidate.source_ref.model_dump(mode="json"),
                    "reasons": [reason.value for reason in candidate.reasons],
                    "paths": [path.model_dump(mode="json") for path in candidate.paths],
                    "reach_status": candidate.reach_status,
                }
                for candidate in inventory.candidates
            ],
            "diagnostics": [item.model_dump(mode="json") for item in inventory.diagnostics],
        }
    )


def _selection_decision_fingerprint(selection: StructuredContextSelection) -> str:
    return _canonical_sha256(
        {
            "contract": _SELECTION_DECISION_CONTRACT,
            "selection_contract_id": selection.contract_id,
            "profile": selection.profile.model_dump(mode="json"),
            "candidate_contract_id": selection.candidate_contract_id,
            "document_key": selection.document_key,
            "document_revision": selection.document_revision,
            "target_clause_id": selection.target_clause_id,
            "target_reference": selection.target_reference,
            "selected": [
                {
                    "candidate_id": entry.candidate.candidate_id,
                    "selection_reason": entry.selection_reason.value,
                    "reach_hints": [hint.value for hint in entry.reach_hints],
                    "semantic_reach_confirmed": entry.semantic_reach_confirmed,
                    "estimated_character_cost": entry.estimated_character_cost,
                }
                for entry in selection.selected
            ],
            "omitted": [
                {
                    "candidate_id": entry.candidate.candidate_id,
                    "reason": entry.reason.value,
                    "detail": entry.detail,
                    "estimated_character_cost": entry.estimated_character_cost,
                }
                for entry in selection.omitted
            ],
            "gaps": [gap.model_dump(mode="json") for gap in selection.gaps],
            "completeness": selection.completeness.value,
            "budget_used_chars": selection.budget_used_chars,
            "budget_remaining_chars": selection.budget_remaining_chars,
        }
    )


def _actual_input_fingerprint(
    *,
    document_key: str,
    document_revision: str,
    target_clause_id: str,
    target_reference: str,
    surfaces: tuple[BoundContextInputSurface, ...],
) -> str:
    return _canonical_sha256(
        {
            "contract": _ACTUAL_INPUT_CONTRACT,
            "document_key": document_key,
            "document_revision": document_revision,
            "target_clause_id": target_clause_id,
            "target_reference": target_reference,
            "surfaces": [surface.model_dump(mode="json") for surface in surfaces],
        }
    )


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
