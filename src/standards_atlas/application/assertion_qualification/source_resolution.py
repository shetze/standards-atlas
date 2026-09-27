"""Resolve candidate evidence against only the frozen AP01 review source surfaces."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from standards_atlas.application.assertion_qualification.audit import AssertionReviewAudit
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionProposalEvidenceSnapshot,
)
from standards_atlas.domain.model import EvidenceSourceKind


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
    """Result of checking one anchor against an immutable frozen source surface."""

    key: FrozenSourceKey
    status: EvidenceResolutionStatus
    reason: str


class FrozenSourceResolver:
    """Resolve body/heading surfaces embedded in the byte-bound review audit.

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

    def resolve(
        self,
        *,
        source_document_key: str,
        anchor: AssertionProposalEvidenceSnapshot,
    ) -> EvidenceResolution:
        key = FrozenSourceKey(
            source_document_key,
            anchor.source_clause_id,
            anchor.source_kind,
        )
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
        if anchor.start_offset is None or anchor.end_offset is None or anchor.content_hash is None:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.UNAVAILABLE,
                reason="anchor does not contain exact offsets and content hash",
            )
        text = unique_texts[0]
        if anchor.end_offset > len(text):
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.INVALID,
                reason="anchor offsets exceed the frozen source surface",
            )
        actual_hash = hashlib.sha256(
            text[anchor.start_offset : anchor.end_offset].encode("utf-8")
        ).hexdigest()
        if actual_hash != anchor.content_hash:
            return EvidenceResolution(
                key=key,
                status=EvidenceResolutionStatus.INVALID,
                reason="anchor content hash does not match the frozen source slice",
            )
        return EvidenceResolution(
            key=key,
            status=EvidenceResolutionStatus.VALID,
            reason="anchor offsets and content hash match the frozen source surface",
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
