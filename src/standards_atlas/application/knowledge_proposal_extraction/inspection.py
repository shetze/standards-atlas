"""Deterministic, model-free inspection of AP02 context and evidence contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.context import ContextSelectionProfile
from standards_atlas.application.context.input_binding import context_source_package_binding
from standards_atlas.application.knowledge_proposal_extraction.context import (
    assertion_context_source_package,
)
from standards_atlas.application.knowledge_proposal_extraction.grounding import (
    EvidenceGroundingRequest,
    MultiSpanEvidenceGroundingResult,
    ground_evidence_request,
)
from standards_atlas.domain.model import Clause, EngineeringDocument

CONTEXT_EVIDENCE_INSPECTION_CONTRACT = "context-evidence-inspection-v1"


class ContextEvidenceInspectionReport(BaseModel):
    """Text-free deterministic report for one source-bound target clause.

    Source bytes are intentionally omitted.  The report exposes source identity, provenance,
    selection, gaps, budget, fingerprints and technical grounding outcomes without claiming
    semantic evidence quality or executing an inference adapter.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["context-evidence-inspection-v1"] = CONTEXT_EVIDENCE_INSPECTION_CONTRACT
    model_execution: Literal[False] = False
    semantic_quality_assessed: Literal[False] = False
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    candidate_contract_id: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    candidate_diagnostics: tuple[dict[str, object], ...] = ()
    selection_contract_id: str = Field(min_length=1)
    selection_profile: dict[str, object]
    selection_completeness: str = Field(min_length=1)
    selected_sources: tuple[dict[str, object], ...] = ()
    omitted_sources: tuple[dict[str, object], ...] = ()
    gaps: tuple[dict[str, object], ...] = ()
    budget: dict[str, int]
    fingerprints: dict[str, str]
    package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    grounding_results: tuple[MultiSpanEvidenceGroundingResult, ...] = ()


def inspect_context_evidence(
    document: EngineeringDocument,
    clause: Clause,
    *,
    profile: ContextSelectionProfile | None = None,
    grounding_requests: tuple[EvidenceGroundingRequest, ...] = (),
) -> ContextEvidenceInspectionReport:
    """Build one complete model-free AP02 inspection from current application services."""

    package = assertion_context_source_package(document, clause, profile=profile)
    binding = context_source_package_binding(package)
    selection = package.selection
    inventory = package.candidate_inventory

    selected_sources = tuple(
        _selected_source_payload(surface) for surface in package.input_surfaces
    )
    omitted_sources = tuple(
        {
            "candidate_id": item.candidate.candidate_id,
            "source_ref": item.candidate.source_ref.model_dump(mode="json"),
            "availability": item.candidate.resolution.availability.value,
            "origin": item.candidate.resolution.origin.value,
            "candidate_reasons": [reason.value for reason in item.candidate.reasons],
            "structural_paths": [path.model_dump(mode="json") for path in item.candidate.paths],
            "omission_reason": item.reason.value,
            "detail": item.detail,
            "estimated_character_cost": item.estimated_character_cost,
        }
        for item in selection.omitted
    )

    return ContextEvidenceInspectionReport(
        document_key=package.document_key,
        document_revision=package.document_revision,
        target_clause_id=package.target_clause_id,
        target_reference=package.target_reference,
        candidate_contract_id=inventory.contract_id,
        candidate_count=len(inventory.candidates),
        candidate_diagnostics=tuple(item.model_dump(mode="json") for item in inventory.diagnostics),
        selection_contract_id=selection.contract_id,
        selection_profile=selection.profile.model_dump(mode="json"),
        selection_completeness=selection.completeness.value,
        selected_sources=selected_sources,
        omitted_sources=omitted_sources,
        gaps=tuple(item.model_dump(mode="json") for item in selection.gaps),
        budget={
            "configured_chars": selection.profile.character_budget,
            "fixed_overhead_chars": selection.profile.fixed_overhead_chars,
            "per_surface_overhead_chars": selection.profile.per_surface_overhead_chars,
            "used_chars": selection.budget_used_chars,
            "remaining_chars": selection.budget_remaining_chars,
        },
        fingerprints=package.fingerprints.model_dump(mode="json"),
        package_sha256=binding.package_sha256,
        grounding_results=tuple(
            ground_evidence_request(package, request) for request in grounding_requests
        ),
    )


def _selected_source_payload(surface) -> dict[str, object]:
    identity = surface.identity
    return {
        "package_source_ref": surface.package_source_ref,
        "document_key": identity.document.document_key,
        "document_revision": identity.document.source_revision,
        "clause_id": identity.clause_id,
        "clause_reference": identity.clause_reference,
        "source_kind": identity.source_kind.value if identity.source_kind is not None else None,
        "media_kind": identity.media_kind.value if identity.media_kind is not None else None,
        "block_id": identity.block_id,
        "origin": surface.origin.value,
        "origin_reference": surface.origin_reference,
        "source_backed": surface.source_backed,
        "rendering_id": surface.rendering_id,
        "surface_sha256": surface.surface_sha256,
        "content_sha256": surface.content_sha256,
        "start_offset": surface.start_offset,
        "end_offset": surface.end_offset,
        "candidate_reasons": [reason.value for reason in surface.candidate_reasons],
        "structural_paths": [path.model_dump(mode="json") for path in surface.structural_paths],
        "selection_reason": surface.selection_reason.value,
        "reach_hints": [hint.value for hint in surface.reach_hints],
        "semantic_reach_confirmed": surface.semantic_reach_confirmed,
    }
