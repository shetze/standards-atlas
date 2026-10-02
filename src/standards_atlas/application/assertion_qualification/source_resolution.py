"""Resolve evaluation evidence against explicitly separated source bases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from standards_atlas.application.assertion_qualification.audit import AssertionReviewAudit
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionProposalEvidenceSnapshot,
)
from standards_atlas.application.context.input_binding import (
    ContextSourcePackage,
    context_source_package_binding,
)
from standards_atlas.domain.model import ContextSourcePackageBinding, EvidenceSourceKind


@dataclass(frozen=True, order=True)
class FrozenSourceKey:
    """Stable identity of one evidence-addressable source surface."""

    source_document_key: str
    clause_id: str
    source_kind: EvidenceSourceKind


class EvidenceResolutionStatus(StrEnum):
    """Technical resolution result; it is not a semantic evidence judgement."""

    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class EvidenceResolution:
    """Result of checking one anchor against one explicitly bound source basis."""

    key: FrozenSourceKey
    status: EvidenceResolutionStatus
    reason: str


class EvidenceSourceResolver(Protocol):
    """Small evaluator-facing resolver contract shared by frozen and native sources."""

    def resolve(
        self,
        *,
        source_document_key: str,
        anchor: AssertionProposalEvidenceSnapshot,
    ) -> EvidenceResolution: ...


class FrozenSourceResolver:
    """Resolve body/heading surfaces embedded in the byte-bound AP01 review audit.

    Only complete, identifiable source surfaces are registered. Context quotations and
    other descriptive fields are deliberately ignored. Multiple different texts for the
    same source key are retained as a conflict rather than silently choosing a version.
    """

    def __init__(self, surfaces: dict[FrozenSourceKey, tuple[str, ...]]) -> None:
        self._surfaces = surfaces

    @classmethod
    def from_audit(cls, audit: AssertionReviewAudit) -> FrozenSourceResolver:
        collected: dict[FrozenSourceKey, list[str]] = {}
        for case in audit.review.cases:
            _add_surface(
                collected,
                FrozenSourceKey(case.document_key, case.clause_id, EvidenceSourceKind.BODY),
                case.text,
            )
            context = case.context
            heading = context.get("heading")
            if isinstance(heading, str):
                _add_surface(
                    collected,
                    FrozenSourceKey(
                        case.document_key,
                        case.clause_id,
                        EvidenceSourceKind.HEADING,
                    ),
                    heading,
                )
            _collect_ancestor_headings(collected, case.document_key, context)
            _collect_associative_context(collected, case.document_key, context)
        return cls({key: tuple(values) for key, values in collected.items()})

    def surface_hashes(self, *, source_document_key: str) -> dict[FrozenSourceKey, tuple[str, ...]]:
        """Return text-free full-surface hashes for source-comparability reporting."""

        return {
            key: tuple(hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts)
            for key, texts in self._surfaces.items()
            if key.source_document_key == source_document_key
        }

    def resolve(
        self,
        *,
        source_document_key: str,
        anchor: AssertionProposalEvidenceSnapshot,
    ) -> EvidenceResolution:
        key = FrozenSourceKey(source_document_key, anchor.source_clause_id, anchor.source_kind)
        texts = self._surfaces.get(key)
        if texts is None:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.UNAVAILABLE,
                reason="source surface is not available in the frozen review context",
            )
        unique_texts = tuple(dict.fromkeys(texts))
        if len(unique_texts) != 1:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.CONFLICTING,
                reason="multiple different frozen texts exist for the same source surface",
            )
        return _resolve_exact_anchor(key, unique_texts[0], 0, anchor, "frozen source surface")


class NativeSourcePackageResolver:
    """Resolve candidate evidence only inside one target's actual bound input package."""

    def __init__(
        self,
        package: ContextSourcePackage,
        binding: ContextSourcePackageBinding,
    ) -> None:
        actual = context_source_package_binding(package)
        if actual != binding:
            raise ValueError("native source package does not match proposal source binding")
        self.package = package
        self.binding = binding

    def surface_hashes(self) -> dict[FrozenSourceKey, tuple[str, ...]]:
        hashes: dict[FrozenSourceKey, list[str]] = {}
        for surface in self.package.input_surfaces:
            if surface.source_ref.source_kind is None:
                continue
            key = FrozenSourceKey(
                self.package.document_key,
                surface.source_ref.clause_id,
                surface.source_ref.source_kind,
            )
            hashes.setdefault(key, []).append(surface.surface_sha256.removeprefix("sha256:"))
        return {key: tuple(dict.fromkeys(values)) for key, values in hashes.items()}

    def resolve(
        self,
        *,
        source_document_key: str,
        anchor: AssertionProposalEvidenceSnapshot,
    ) -> EvidenceResolution:
        key = FrozenSourceKey(source_document_key, anchor.source_clause_id, anchor.source_kind)
        if source_document_key != self.package.document_key:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.UNAVAILABLE,
                reason="anchor document is outside the bound native source package",
            )
        matches = tuple(
            surface
            for surface in self.package.input_surfaces
            if surface.source_ref.document_key == source_document_key
            and surface.source_ref.clause_id == anchor.source_clause_id
            and surface.source_ref.source_kind == anchor.source_kind
        )
        if not matches:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.UNAVAILABLE,
                reason="anchor source surface was not delivered in the bound native input package",
            )
        if anchor.start_offset is None or anchor.end_offset is None or anchor.content_hash is None:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.UNAVAILABLE,
                reason="anchor does not contain exact offsets and content hash",
            )

        containing = tuple(
            surface
            for surface in matches
            if surface.start_offset <= anchor.start_offset
            and anchor.end_offset <= surface.end_offset
        )
        if not containing:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.INVALID,
                reason="anchor offsets fall outside the delivered native source excerpt",
            )
        outcomes = tuple(
            _resolve_exact_anchor(
                key,
                surface.text,
                surface.start_offset,
                anchor,
                "bound native source excerpt",
            )
            for surface in containing
        )
        valid = tuple(item for item in outcomes if item.status is EvidenceResolutionStatus.VALID)
        if len(valid) == 1:
            return valid[0]
        if len(valid) > 1:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.CONFLICTING,
                reason="multiple delivered native excerpts satisfy the same evidence anchor",
            )
        return outcomes[0]


def _resolve_exact_anchor(
    key: FrozenSourceKey,
    text: str,
    base_offset: int,
    anchor: AssertionProposalEvidenceSnapshot,
    source_label: str,
) -> EvidenceResolution:
    if anchor.start_offset is None or anchor.end_offset is None or anchor.content_hash is None:
        return EvidenceResolution(
            key=key,
            status=EvidenceResolutionStatus.UNAVAILABLE,
            reason="anchor does not contain exact offsets and content hash",
        )
    start = anchor.start_offset - base_offset
    end = anchor.end_offset - base_offset
    if start < 0 or end > len(text):
        return EvidenceResolution(
            key=key,
            status=EvidenceResolutionStatus.INVALID,
            reason=f"anchor offsets exceed the {source_label}",
        )
    actual_hash = hashlib.sha256(text[start:end].encode("utf-8")).hexdigest()
    if actual_hash != anchor.content_hash:
        return EvidenceResolution(
            key=key,
            status=EvidenceResolutionStatus.INVALID,
            reason=f"anchor content hash does not match the {source_label} slice",
        )
    return EvidenceResolution(
        key=key,
        status=EvidenceResolutionStatus.VALID,
        reason=f"anchor offsets and content hash match the {source_label}",
    )


def _add_surface(
    collected: dict[FrozenSourceKey, list[str]], key: FrozenSourceKey, text: str
) -> None:
    collected.setdefault(key, []).append(text)


def _collect_ancestor_headings(
    collected: dict[FrozenSourceKey, list[str]],
    document_key: str,
    context: dict[str, Any],
) -> None:
    headings = context.get("ancestor_headings")
    if not isinstance(headings, list):
        return
    for item in headings:
        if not isinstance(item, dict):
            continue
        clause_id = item.get("clause_id")
        heading = item.get("heading")
        if isinstance(clause_id, str) and isinstance(heading, str):
            _add_surface(
                collected,
                FrozenSourceKey(document_key, clause_id, EvidenceSourceKind.HEADING),
                heading,
            )


def _collect_associative_context(
    collected: dict[FrozenSourceKey, list[str]],
    document_key: str,
    context: dict[str, Any],
) -> None:
    entries = context.get("associative_context")
    if not isinstance(entries, list):
        return
    for item in entries:
        if not isinstance(item, dict):
            continue
        clause_id = item.get("clause_id")
        if not isinstance(clause_id, str):
            continue
        text = item.get("text")
        if isinstance(text, str):
            _add_surface(
                collected,
                FrozenSourceKey(document_key, clause_id, EvidenceSourceKind.BODY),
                text,
            )
        heading = item.get("heading")
        if isinstance(heading, str):
            _add_surface(
                collected,
                FrozenSourceKey(document_key, clause_id, EvidenceSourceKind.HEADING),
                heading,
            )
