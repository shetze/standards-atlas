"""High-recall deterministic extraction of structural reference mentions."""

from __future__ import annotations

import re

from standards_atlas.domain.model.reference_mention import (
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
)

_REFERENCE = r"\d+(?:\.\d+){0,7}(?:[a-z])?"
_EXPLICIT = re.compile(
    rf"\b(?P<prefix>clauses?|subclauses?|paragraphs?|sections?)\s+(?P<reference>{_REFERENCE})\b",
    re.I,
)
_RANGE = re.compile(
    rf"\b(?P<prefix>clauses?|subclauses?|paragraphs?|sections?)\s+(?P<start>{_REFERENCE})\s*(?:to|through|–|—|-)\s*(?P<end>{_REFERENCE})\b",
    re.I,
)
_CONTEXTUAL = re.compile(
    r"\b(?:(?P<this>this)\s+(?:sub)?clause|(?:the\s+)?(?P<following>following)\s+(?:sub)?clauses?|(?:the\s+)?(?P<preceding>preceding|previous)\s+(?:sub)?clauses?)\b",
    re.I,
)


def extract_reference_mentions(text: str) -> tuple[ReferenceMention, ...]:
    mentions: list[ReferenceMention] = []
    occupied: list[tuple[int, int]] = []
    for match in _RANGE.finditer(text):
        occupied.append(match.span())
        mentions.append(
            ReferenceMention(
                kind=ReferenceMentionKind.CLAUSE_RANGE,
                surface_text=match.group(0),
                start_offset=match.start(),
                end_offset=match.end(),
                range_start=match.group("start"),
                range_end=match.group("end"),
                cardinality_hint="multiple",
                status=ReferenceResolutionStatus.UNRESOLVED,
            )
        )
    for match in _EXPLICIT.finditer(text):
        if any(a <= match.start() < b for a, b in occupied):
            continue
        mentions.append(
            ReferenceMention(
                kind=ReferenceMentionKind.CLAUSE,
                surface_text=match.group(0),
                start_offset=match.start(),
                end_offset=match.end(),
                reference=match.group("reference"),
                cardinality_hint="one",
                status=ReferenceResolutionStatus.UNRESOLVED,
            )
        )
    for match in _CONTEXTUAL.finditer(text):
        direction = (
            "self"
            if match.group("this")
            else ("forward" if match.group("following") else "backward")
        )
        cardinality = "one" if direction == "self" else "multiple"
        mentions.append(
            ReferenceMention(
                kind=ReferenceMentionKind.CONTEXTUAL_CLAUSE,
                surface_text=match.group(0),
                start_offset=match.start(),
                end_offset=match.end(),
                direction_hint=direction,
                cardinality_hint=cardinality,
                status=ReferenceResolutionStatus.DEFERRED,
            )
        )
    return tuple(sorted(mentions, key=lambda m: (m.start_offset, m.end_offset)))


def resolve_document_reference_mentions(document):
    """Resolve explicit same-document mentions while retaining every mention."""
    from standards_atlas.domain.model.reference_mention import ReferenceTarget

    by_ref: dict[tuple[str | None, str], list] = {}
    for clause in document.clauses:
        key = (clause.reference.part, clause.reference.clause.strip().casefold())
        by_ref.setdefault(key, []).append(clause)
    clauses = []
    for clause in document.clauses:
        resolved = []
        for mention in clause.reference_mentions:
            if not mention.reference:
                resolved.append(mention)
                continue
            key = (clause.reference.part, mention.reference.strip().casefold())
            candidates = [c for c in by_ref.get(key, ()) if c.id != clause.id]
            if len(candidates) == 1:
                target = candidates[0]
                resolved.append(
                    mention.model_copy(
                        update={
                            "status": ReferenceResolutionStatus.RESOLVED,
                            "targets": (
                                ReferenceTarget(
                                    document_key=document.key.value,
                                    clause_id=target.id.value,
                                    reference=target.reference.clause,
                                    title=target.heading,
                                ),
                            ),
                        }
                    )
                )
            elif len(candidates) > 1:
                resolved.append(
                    mention.model_copy(
                        update={
                            "status": ReferenceResolutionStatus.AMBIGUOUS,
                            "targets": tuple(
                                ReferenceTarget(
                                    document_key=document.key.value,
                                    clause_id=c.id.value,
                                    reference=c.reference.clause,
                                    title=c.heading,
                                )
                                for c in candidates
                            ),
                        }
                    )
                )
            else:
                resolved.append(mention)
        clauses.append(clause.model_copy(update={"reference_mentions": tuple(resolved)}))
    return document.model_copy(update={"clauses": tuple(clauses)})
