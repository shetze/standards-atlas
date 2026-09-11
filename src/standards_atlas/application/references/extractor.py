"""Lossless reference extraction; resolution uses the same TOC index as routing."""

from __future__ import annotations

import re

from standards_atlas.application.references.resolution import (
    DocumentReferenceIndex,
    canonical_reference,
)
from standards_atlas.application.references.syntax import (
    MULTI_LETTER_OBJECT_COORDINATE,
    OBJECT_PREFIX,
)
from standards_atlas.domain.model import EngineeringDocument
from standards_atlas.domain.model.reference_mention import (
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
    ReferenceTarget,
)

REFERENCE_EXTRACTOR_VERSION = "reference-mention-extractor/v4"
_LEGACY_EXTRACTOR_VERSION = "reference-mention-extractor/v3"

_NUMBER = r"\d+(?:\.\d+){0,7}(?:[a-z])?"
_ANNEX = r"[A-Z](?:\.\d+){0,7}"
_ITEM = rf"(?:{_NUMBER}|{_ANNEX})"
_PREFIX = (
    r"(?:clauses?|subclauses?|paragraphs?|sections?|annex(?:es)?|"
    r"appendi(?:x|ces)|tables?|figures?|figs?\.?)"
)
_TAIL = rf"(?:\s*(?:to|through|–|—|-|,\s*(?:and\s+)?|\band\b|&)\s*(?:{_PREFIX}\s+)?{_ITEM})*"
_STANDARD = r"(?:IEC|ISO|EN|DIN|BS|IEEE)(?:[/ -](?:IEC|ISO|EN))*\s*\d+(?:-\d+)*(?::\d{4})?"
# Qualified mentions are collected first so their numeric suffixes cannot leak
# into the local namespace as independent bare references.
_QUALIFIED = re.compile(
    rf"\b(?P<standard>{_STANDARD})\s*[,;]?\s+"
    rf"(?P<coordinate>(?:{_PREFIX}\s+)?{_ITEM}{_TAIL})\b",
    re.I,
)
# One coordinate may be shared by several explicitly named standards. Keep the
# complete source span for each target; never manufacture an excerpt for it.
_STANDARD_LIST = rf"{_STANDARD}(?:\s*(?:,\s*(?:and\s+)?|\band\b|&)\s*{_STANDARD})*"
_SUFFIX_QUALIFIED = re.compile(
    rf"\b(?P<coordinate>(?:{_PREFIX}\s+)?{_ITEM}{_TAIL})\s+of\s+"
    rf"(?P<standards>{_STANDARD_LIST})\b",
    re.I,
)
_EXPLICIT = re.compile(rf"\b{_PREFIX}\s+{_ITEM}{_TAIL}\b", re.I)
_BARE = re.compile(rf"(?<![\w.:/-])\d+(?:\.\d+){{1,7}}[a-z]?{_TAIL}\b", re.I)
_SCIENTIFIC_NUMBER = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?[eE][+-]?\d+(?![\w]|\.\d)")
_CONTEXTUAL = re.compile(
    r"\b(?:(?P<this>this)\s+(?:(?:sub)?clause|section)|"
    r"(?:the\s+)?(?P<following>following)\s+(?:sub)?clauses?|"
    r"(?:the\s+)?(?P<preceding>preceding|previous)\s+(?:sub)?clauses?)\b",
    re.I,
)
_RANGE = re.compile(rf"({_ITEM})\s*(?:to|through|–|—|-)\s*({_ITEM})\b", re.I)


# Keep the exact previous grammar for per-input fingerprint compatibility checks.
_LEGACY_QUALIFIED, _LEGACY_SUFFIX_QUALIFIED = _QUALIFIED, _SUFFIX_QUALIFIED
_LEGACY_EXPLICIT, _LEGACY_RANGE = _EXPLICIT, _RANGE
_OBJECT_ITEM = rf"(?:{_ITEM}|{MULTI_LETTER_OBJECT_COORDINATE})"
_LABELLED_START = rf"(?:{OBJECT_PREFIX}\s+{_OBJECT_ITEM}|{_PREFIX}\s+{_ITEM})"
_MODERN_TAIL = (
    rf"(?:\s*(?:to|through|–|—|-|,\s*(?:and\s+)?|\band\b|&)"
    rf"\s*(?:{_PREFIX}\s+)?{_OBJECT_ITEM})*"
)
_QUALIFIED = re.compile(
    rf"\b(?P<standard>{_STANDARD})\s*[,;]?\s+"
    rf"(?P<coordinate>(?:{_LABELLED_START}|{_ITEM}){_MODERN_TAIL})\b",
    re.I,
)
_SUFFIX_QUALIFIED = re.compile(
    rf"\b(?P<coordinate>(?:{_LABELLED_START}|{_ITEM}){_MODERN_TAIL})\s+of\s+"
    rf"(?P<standards>{_STANDARD_LIST})\b",
    re.I,
)
_EXPLICIT = re.compile(rf"\b{_LABELLED_START}{_MODERN_TAIL}\b", re.I)
_RANGE = re.compile(
    rf"({_OBJECT_ITEM})\s*(?:to|through|–|—|-)\s*"
    rf"(?:{OBJECT_PREFIX}\s+)?({_OBJECT_ITEM})\b",
    re.I,
)
_COORDINATE_MEMBERS = re.compile(
    rf"\b(?:(?P<label>{_PREFIX})\s+)?(?P<coordinate>{_OBJECT_ITEM})\b", re.I
)


def _labelled_multi_objects_only(coordinate: str) -> bool:
    object_label = False
    for match in _COORDINATE_MEMBERS.finditer(coordinate):
        if match.group("label"):
            object_label = bool(re.fullmatch(OBJECT_PREFIX, match.group("label"), re.I))
        if (
            re.fullmatch(MULTI_LETTER_OBJECT_COORDINATE, match.group("coordinate"), re.I)
            and not object_label
        ):
            return False
    return True


def extract_reference_mentions(text: str) -> tuple[ReferenceMention, ...]:
    return _extract_reference_mentions(text)


def reference_extraction_version(
    text: str, *, mentions: tuple[ReferenceMention, ...] | None = None
) -> str:
    """Keep unchanged model inputs reusable across a source-local extractor fix.

    The v3 compatibility label is used only after exact mention equality, including
    source spans. Changed extraction receives the new version and a new input hash.
    """
    current = extract_reference_mentions(text) if mentions is None else mentions
    if _extract_reference_mentions(text, legacy=True) == current:
        return _LEGACY_EXTRACTOR_VERSION
    return REFERENCE_EXTRACTOR_VERSION


def _extract_reference_mentions(text: str, *, legacy: bool = False) -> tuple[ReferenceMention, ...]:
    mentions: list[ReferenceMention] = []
    occupied: list[tuple[int, int]] = []
    scientific_spans = [match.span() for match in _SCIENTIFIC_NUMBER.finditer(text)]
    # Protect standalone standard designations too (e.g. their edition numbers).
    standard_spans = [match.span() for match in re.finditer(_STANDARD, text, re.I)]
    patterns = (
        (_LEGACY_QUALIFIED, _LEGACY_SUFFIX_QUALIFIED, _LEGACY_EXPLICIT, _BARE)
        if legacy
        else (
            _QUALIFIED,
            _LEGACY_QUALIFIED,
            _SUFFIX_QUALIFIED,
            _LEGACY_SUFFIX_QUALIFIED,
            _EXPLICIT,
            _LEGACY_EXPLICIT,
            _BARE,
        )
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            if any(a < match.end() and match.start() < b for a, b in occupied):
                continue
            if pattern is _BARE and any(
                a < match.end() and match.start() < b for a, b in standard_spans
            ):
                continue
            if (
                not legacy
                and pattern is _BARE
                and any(a <= match.start() and match.end() <= b for a, b in scientific_spans)
            ):
                # Only bare tokens contained in a complete scientific number.
                # Explicit Clause/Table/Figure and qualified citations take priority.
                continue
            surface = match.group(0)
            coordinate = surface
            references = (surface,)
            if pattern in (_SUFFIX_QUALIFIED, _LEGACY_SUFFIX_QUALIFIED):
                coordinate = match.group("coordinate")
                references = tuple(
                    f"{standard.group(0)} {coordinate}"
                    for standard in re.finditer(_STANDARD, match.group("standards"), re.I)
                )
            elif pattern in (_QUALIFIED, _LEGACY_QUALIFIED):
                coordinate = match.group("coordinate")
                references = (f"{match.group('standard')} {coordinate}",)
            elif re.fullmatch(
                rf"(?:clauses?|subclauses?|paragraphs?|sections?)\s+{_NUMBER}", surface, re.I
            ):
                references = (surface.split()[-1],)
            # Standard designators (61508-5, 26262-3:2018, ...) are identities,
            # never coordinate ranges. Lists do not become ranges either.
            if not legacy and not _labelled_multi_objects_only(coordinate):
                continue
            bounds = (_LEGACY_RANGE if legacy else _RANGE).search(coordinate)
            for reference in references:
                mentions.append(
                    ReferenceMention(
                        kind=(
                            ReferenceMentionKind.CLAUSE_RANGE
                            if bounds
                            else ReferenceMentionKind.CLAUSE
                        ),
                        surface_text=surface,
                        start_offset=match.start(),
                        end_offset=match.end(),
                        reference=reference,
                        range_start=bounds.group(1) if bounds else None,
                        range_end=bounds.group(2) if bounds else None,
                        cardinality_hint=(
                            "multiple" if bounds or re.search(r"\band\b|,|&", coordinate) else "one"
                        ),
                        status=ReferenceResolutionStatus.UNRESOLVED,
                    )
                )
            occupied.append(match.span())
    for match in _CONTEXTUAL.finditer(text):
        direction = (
            "self"
            if match.group("this")
            else ("forward" if match.group("following") else "backward")
        )
        mentions.append(
            ReferenceMention(
                kind=ReferenceMentionKind.CONTEXTUAL_CLAUSE,
                surface_text=match.group(0),
                start_offset=match.start(),
                end_offset=match.end(),
                direction_hint=direction,
                cardinality_hint="one" if direction == "self" else "multiple",
                status=ReferenceResolutionStatus.DEFERRED,
            )
        )
    return tuple(sorted(mentions, key=lambda mention: (mention.start_offset, mention.end_offset)))


def resolve_reference_mentions(
    mentions: tuple[ReferenceMention, ...],
    source_clause_id: str,
    index: DocumentReferenceIndex,
) -> tuple[ReferenceMention, ...]:
    resolved = []
    for mention in mentions:
        text = mention.reference
        if mention.direction_hint == "self":
            text = mention.surface_text
        if not text:
            resolved.append(mention)
            continue
        result = index.resolve_group(text, source_clause_id)
        resolved.append(
            mention.model_copy(
                update={
                    "status": ReferenceResolutionStatus(result.status),
                    "targets": tuple(
                        ReferenceTarget(
                            document_key=index.document_key,
                            clause_id=target.id.value,
                            reference=canonical_reference(target),
                            title=target.heading,
                        )
                        for target in result.targets
                    ),
                }
            )
        )
    return tuple(resolved)


def resolve_document_reference_mentions(document: EngineeringDocument) -> EngineeringDocument:
    """Resolve full coordinates, lists and ranges without silently using a parent."""
    index = DocumentReferenceIndex(document)
    return document.model_copy(
        update={
            "clauses": tuple(
                clause.with_baseline_updates(
                    reference_mentions=resolve_reference_mentions(
                        clause.reference_mentions, clause.id.value, index
                    )
                )
                for clause in document.clauses
            )
        }
    )


def refresh_document_references(document: EngineeringDocument) -> EngineeringDocument:
    """Refresh generated mention/structural-reference context without any LLM call."""
    from standards_atlas.domain.model import (
        GeneratedAttribute,
        GenerationMethod,
        StructuralReferenceEdge,
    )

    index = DocumentReferenceIndex(document)
    clauses = []
    for clause in document.clauses:
        updated = clause
        if clause.plain_text.strip() and not clause.provenance.protection(
            "baseline.reference_mentions"
        ):
            mentions = resolve_reference_mentions(
                extract_reference_mentions(clause.plain_text), clause.id.value, index
            )
            if mentions != clause.reference_mentions:
                updated = updated.with_baseline_updates(reference_mentions=mentions).mark_generated(
                    GeneratedAttribute(
                        path="baseline.reference_mentions",
                        generator=REFERENCE_EXTRACTOR_VERSION,
                        method=GenerationMethod.DETERMINISTIC,
                    )
                )
        structural = updated.structural_context
        if structural and not updated.provenance.protection("baseline.structural_context"):
            edges = []
            for mention in updated.reference_mentions:
                for target in mention.targets or (None,):
                    edges.append(
                        StructuralReferenceEdge(
                            source_clause_id=clause.id.value,
                            target_clause_id=target.clause_id if target else None,
                            target_reference=target.reference if target else mention.reference,
                            status=mention.status.value,
                            surface_text=mention.surface_text,
                        )
                    )
            if tuple(edges) != structural.references:
                updated = updated.with_baseline_updates(
                    structural_context=structural.model_copy(update={"references": tuple(edges)})
                )
        clauses.append(updated)
    return document.model_copy(update={"clauses": tuple(clauses)})
