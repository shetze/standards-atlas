"""Generate AtlasData TOC initialization records from domain documents."""

from __future__ import annotations

import hashlib

from standards_atlas.adapters.atlasdata.parser import InitializationRecord
from standards_atlas.domain.model import Clause, ClauseType, EngineeringDocument


_TYPE_MARKERS: dict[ClauseType, str] = {
    ClauseType.TOC: "u",
    ClauseType.CLAUSE: "u",
    ClauseType.REQUIREMENT: "r",
    ClauseType.SCOPE: "s",
    ClauseType.TERM: "t",
    ClauseType.OBJECTIVE: "o",
    ClauseType.MISC: "m",
}


_DEFAULT_HEADINGS: dict[ClauseType, str] = {
    ClauseType.TOC: "Heading",
    ClauseType.CLAUSE: "Heading",
    ClauseType.REQUIREMENT: "Requirement",
    ClauseType.SCOPE: "Scope",
    ClauseType.TERM: "Term",
    ClauseType.OBJECTIVE: "Objective",
    ClauseType.MISC: "Misc",
}


def generate_toc_records(document: EngineeringDocument) -> list[InitializationRecord]:
    """Generate TOC records for all clauses in a document."""
    return [_generate_toc_record(clause) for clause in document.clauses]


def _generate_toc_record(clause: Clause) -> InitializationRecord:
    reference = clause.reference.as_text()

    return InitializationRecord(
        kind="TOC",
        hash_value=_hash_reference(reference),
        reference=reference,
        content=_heading_content(clause),
        type_marker=_type_marker(clause),
    )


def _heading_content(clause: Clause) -> str:
    if clause.title and clause.title.strip():
        return clause.title.strip()

    return _DEFAULT_HEADINGS.get(clause.clause_type, "Heading")


def _type_marker(clause: Clause) -> str:
    return _TYPE_MARKERS.get(clause.clause_type, "u")


def _hash_reference(reference: str) -> str:
    return hashlib.md5(reference.encode("utf-8")).hexdigest()
