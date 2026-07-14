"""Deterministic detection of clause-reference candidates."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

from standards_atlas import __version__
from standards_atlas.application.model.normalized_document import (
    NormalizedExtractedDocument,
    NormalizedHeading,
    NormalizedText,
)
from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceCandidateStatus,
    ReferenceDetectionIssue,
    ReferenceDetectionMetadata,
    ReferenceDetectionStatistics,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import EngineeringDocument

_NUMERIC = re.compile(r"^\s*(?P<ref>\d+(?:\s*[.]\s*\d+)*)(?:[.]?)\s*(?P<title>.*)$")
_ANNEX_PREFIX = re.compile(
    r"^\s*(?:annex|appendix)\s+(?P<ref>[A-Z]{1,3}(?:\s*[.]\s*\d+)*)\s*(?P<title>.*)$",
    re.IGNORECASE,
)
_ANNEX_BARE = re.compile(r"^\s*(?P<ref>[A-Z]{1,3}(?:\s*[.]\s*\d+)*)(?:[.]?)\s+(?P<title>.+)$")
_MAX_FOLLOWING_LABEL_LENGTH = 120


class ReferenceCandidateDetector:
    """Find likely clause starts and validate them against AtlasData structure."""

    def detect(
        self,
        normalized: NormalizedExtractedDocument,
        engineering_document: EngineeringDocument,
    ) -> ReferenceCandidateDocument:
        expected = self._expected_index(engineering_document)
        candidates: list[ReferenceCandidate] = []
        issues: list[ReferenceDetectionIssue] = []

        for index, item in enumerate(normalized.items):
            if not isinstance(item, (NormalizedHeading, NormalizedText)):
                continue
            is_heading = isinstance(item, NormalizedHeading)
            parsed = self._parse(item.text, is_heading=is_heading)
            if parsed is None:
                continue
            raw, reference, remainder, kind, confidence = parsed
            clause_ids = expected.get(reference, ())
            status = (
                ReferenceCandidateStatus.EXPECTED
                if len(clause_ids) == 1
                else ReferenceCandidateStatus.AMBIGUOUS
                if len(clause_ids) > 1
                else ReferenceCandidateStatus.UNEXPECTED
            )
            remainder_kind = self._remainder_kind(remainder, is_heading=is_heading)
            following_item_id, following_label = self._following_label(
                normalized,
                index,
                has_inline_remainder=bool(remainder),
            )
            candidate = ReferenceCandidate(
                item_id=item.id,
                sequence_number=item.sequence_number,
                raw_reference=raw,
                normalized_reference=reference,
                title_remainder=remainder or None,
                remainder_kind=remainder_kind,
                following_label_item_id=following_item_id,
                following_label=following_label,
                match_kind=kind,
                status=status,
                confidence=(
                    confidence
                    if status is not ReferenceCandidateStatus.UNEXPECTED
                    else min(confidence, 0.45)
                ),
                expected_clause_ids=clause_ids,
            )
            candidates.append(candidate)
            if status is ReferenceCandidateStatus.UNEXPECTED:
                issues.append(
                    ReferenceDetectionIssue(
                        code="UNEXPECTED_REFERENCE",
                        item_ids=(item.id,),
                        message=(
                            f"Detected reference {reference!r} "
                            "is not present in the engineering document."
                        ),
                    )
                )
            elif status is ReferenceCandidateStatus.AMBIGUOUS:
                issues.append(
                    ReferenceDetectionIssue(
                        code="AMBIGUOUS_REFERENCE",
                        item_ids=(item.id,),
                        message=f"Reference {reference!r} maps to multiple clauses.",
                    )
                )

        statistics = self._statistics(normalized, candidates)
        return ReferenceCandidateDocument(
            source_id=normalized.source_id,
            candidates=tuple(candidates),
            issues=tuple(issues),
            metadata=ReferenceDetectionMetadata(
                detector_version=__version__,
                source_normalization_hash=_hash_model(normalized),
                expected_structure_hash=_structure_hash(engineering_document),
                created_at=datetime.now(UTC),
                statistics=statistics,
            ),
        )

    @staticmethod
    def _expected_index(document: EngineeringDocument) -> dict[str, tuple[str, ...]]:
        index: dict[str, list[str]] = {}
        for clause in document.clauses:
            reference = _normalize_reference(clause.reference.clause)
            index.setdefault(reference, []).append(clause.id.value)
        return {reference: tuple(ids) for reference, ids in index.items()}

    @staticmethod
    def _parse(text: str, *, is_heading: bool):
        annex = _ANNEX_PREFIX.match(text)
        if annex:
            raw = annex.group("ref")
            return (
                raw,
                _normalize_reference(raw),
                annex.group("title").strip(),
                ReferenceMatchKind.ANNEX,
                0.98,
            )

        numeric = _NUMERIC.match(text)
        if numeric:
            raw = numeric.group("ref")
            reference = _normalize_reference(raw)
            remainder = numeric.group("title").strip()
            kind = ReferenceMatchKind.EXACT if raw == reference else ReferenceMatchKind.NORMALIZED
            confidence = 0.99 if is_heading else 0.82 if not remainder else 0.78
            return raw, reference, remainder, kind, confidence

        if is_heading:
            bare = _ANNEX_BARE.match(text)
            if bare:
                raw = bare.group("ref")
                return (
                    raw,
                    _normalize_reference(raw),
                    bare.group("title").strip(),
                    ReferenceMatchKind.ANNEX,
                    0.93,
                )
        return None

    @staticmethod
    def _remainder_kind(
        remainder: str,
        *,
        is_heading: bool,
    ) -> CandidateRemainderKind:
        if not remainder:
            return CandidateRemainderKind.UNKNOWN
        return CandidateRemainderKind.TITLE if is_heading else CandidateRemainderKind.CONTENT

    @staticmethod
    def _following_label(
        normalized: NormalizedExtractedDocument,
        index: int,
        *,
        has_inline_remainder: bool,
    ) -> tuple[str | None, str | None]:
        if has_inline_remainder or index + 1 >= len(normalized.items):
            return None, None
        following = normalized.items[index + 1]
        if not isinstance(following, (NormalizedHeading, NormalizedText)):
            return None, None
        label = following.text.strip()
        if not label or len(label) > _MAX_FOLLOWING_LABEL_LENGTH:
            return None, None
        if _NUMERIC.match(label) or _ANNEX_PREFIX.match(label):
            return None, None
        return following.id, label

    @staticmethod
    def _statistics(normalized, candidates):
        by_status = {status: 0 for status in ReferenceCandidateStatus}
        by_kind = {kind: 0 for kind in ReferenceMatchKind}
        for candidate in candidates:
            by_status[candidate.status] += 1
            by_kind[candidate.match_kind] += 1
        return ReferenceDetectionStatistics(
            input_items=len(normalized.items),
            candidates=len(candidates),
            expected_candidates=by_status[ReferenceCandidateStatus.EXPECTED],
            unexpected_candidates=by_status[ReferenceCandidateStatus.UNEXPECTED],
            ambiguous_candidates=by_status[ReferenceCandidateStatus.AMBIGUOUS],
            exact_matches=by_kind[ReferenceMatchKind.EXACT],
            normalized_matches=by_kind[ReferenceMatchKind.NORMALIZED],
            inline_matches=by_kind[ReferenceMatchKind.INLINE],
            annex_matches=by_kind[ReferenceMatchKind.ANNEX],
        )


def _normalize_reference(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip().rstrip("."))
    return compact.upper() if compact[:1].isalpha() else compact


def _hash_model(model) -> str:
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _structure_hash(document: EngineeringDocument) -> str:
    payload = [
        (
            clause.id.value,
            clause.reference.clause,
            clause.parent_id.value if clause.parent_id else None,
        )
        for clause in document.clauses
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
