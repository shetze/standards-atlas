"""Current source-bound request helpers shared by extractor and verifier."""

from __future__ import annotations

import hashlib

from standards_atlas.application.context.input_binding import (
    ContextSourcePackage,
    context_source_package_binding,
)
from standards_atlas.domain.model import EvidenceAnchor, EvidenceSourceKind

KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT = "source-bound-knowledge-proposal-request-v1"
KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT = "source-bound-knowledge-proposal-output-v1"
ASSERTION_VERIFIER_REQUEST_CONTRACT = "source-bound-assertion-verifier-request-v1"


def source_package_request_payload(package: ContextSourcePackage) -> dict[str, object]:
    """Render only the exact selected source surfaces from one immutable package.

    Candidate inventory text and omitted sources are intentionally excluded.  Their identities,
    omissions and gaps remain visible through the selection metadata and package fingerprints.
    """

    binding = context_source_package_binding(package)
    return {
        "binding": binding.model_dump(mode="json"),
        "selection": {
            "contract_id": package.selection.contract_id,
            "profile_id": package.selection.profile.profile_id,
            "completeness": package.selection.completeness.value,
            "gaps": [gap.model_dump(mode="json") for gap in package.selection.gaps],
            "omitted": [
                {
                    "candidate_id": item.candidate.candidate_id,
                    "source_ref": item.candidate.source_ref.model_dump(mode="json"),
                    "reason": item.reason.value,
                    "detail": item.detail,
                }
                for item in package.selection.omitted
            ],
            "budget_used_chars": package.selection.budget_used_chars,
            "budget_remaining_chars": package.selection.budget_remaining_chars,
        },
        "source_surfaces": [
            {
                "source_ref": surface.package_source_ref,
                "document_key": surface.source_ref.document_key,
                "clause_id": surface.identity.clause_id,
                "source_kind": (
                    surface.source_ref.source_kind.value
                    if surface.source_ref.source_kind is not None
                    else None
                ),
                "start_offset": surface.start_offset,
                "end_offset": surface.end_offset,
                "rendering_id": surface.rendering_id,
                "surface_sha256": surface.surface_sha256,
                "content_sha256": surface.content_sha256,
                "origin": surface.origin.value,
                "source_backed": surface.source_backed,
                "selection_reason": surface.selection_reason.value,
                "reach_hints": [item.value for item in surface.reach_hints],
                "semantic_reach_confirmed": surface.semantic_reach_confirmed,
                "text": surface.text,
            }
            for surface in package.input_surfaces
        ],
    }


def anchor_payload_from_source_package(
    anchor: EvidenceAnchor,
    package: ContextSourcePackage,
) -> dict[str, object]:
    """Resolve one text anchor only inside the exact delivered source package."""

    if anchor.source_kind not in {EvidenceSourceKind.BODY, EvidenceSourceKind.HEADING}:
        raise ValueError("verifier cannot render an unsupported evidence source surface")
    if anchor.start_offset is None or anchor.end_offset is None:
        raise ValueError("current source-bound verifier requires exact evidence offsets")

    matches = [
        surface
        for surface in package.input_surfaces
        if surface.identity.clause_id == anchor.source_clause_id.value
        and surface.source_ref.source_kind is anchor.source_kind
        and anchor.start_offset >= surface.start_offset
        and anchor.end_offset <= surface.end_offset
    ]
    if len(matches) != 1:
        raise ValueError(
            "verifier evidence anchor is not uniquely contained in the bound source package"
        )
    surface = matches[0]
    local_start = anchor.start_offset - surface.start_offset
    local_end = anchor.end_offset - surface.start_offset
    quote = surface.text[local_start:local_end]
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    if anchor.content_hash is None or digest != anchor.content_hash:
        raise ValueError("verifier evidence anchor hash does not match the bound source package")
    return {
        "anchor_id": anchor.id,
        "source_ref": surface.package_source_ref,
        "source_clause_id": anchor.source_clause_id.value,
        "source_kind": anchor.source_kind.value,
        "start_offset": anchor.start_offset,
        "end_offset": anchor.end_offset,
        "content_hash": anchor.content_hash,
        "quote": quote,
    }
