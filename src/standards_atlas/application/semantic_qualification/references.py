"""Deterministic clause-reference extraction and document-local resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.domain.model import Clause, EngineeringDocument

_REFERENCE = r"\d+(?:\.\d+){1,7}(?:[a-z])?"
_RANGE_RE = re.compile(
    rf"(?P<prefix>requirements?|clauses?|subclauses?|paragraphs?)?\s*"
    rf"(?P<start>{_REFERENCE})\s*(?:to|through|–|—|-)\s*(?P<end>{_REFERENCE})",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    rf"(?P<prefix>requirements?|clauses?|subclauses?|paragraphs?|see|according\s+to|under|in)?"
    rf"\s*(?P<reference>{_REFERENCE})",
    re.IGNORECASE,
)


class ReferenceKind(StrEnum):
    """Syntactic kind of an extracted reference."""

    CLAUSE = "clause"
    CLAUSE_RANGE = "clause_range"


class ReferenceResolutionStatus(StrEnum):
    """Outcome of resolving a reference against one EngineeringDocument."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ResolvedReferenceTarget(BaseModel):
    """Resolved target clause with readable and stable identity."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    heading: str | None = Field(default=None, validation_alias=AliasChoices("heading", "title"))


class ClauseReferenceOccurrence(BaseModel):
    """One extracted source expression and its resolution evidence."""

    model_config = ConfigDict(frozen=True)

    kind: ReferenceKind
    surface_text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    reference: str | None = None
    range_start: str | None = None
    range_end: str | None = None
    document_scope: str = "same_document"
    status: ReferenceResolutionStatus
    targets: tuple[ResolvedReferenceTarget, ...] = ()
    unresolved_references: tuple[str, ...] = ()


class ClauseReferenceAnalysis(BaseModel):
    """Versioned reference analysis for one source clause."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    knowledge_domain: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    clause_reference: str = Field(min_length=1)
    clause_title: str | None = None
    references: tuple[ClauseReferenceOccurrence, ...] = ()

    @property
    def clause_key(self) -> str:
        return f"{self.knowledge_domain}:{self.document_key}:{self.clause_id}"


@dataclass(frozen=True)
class ReferenceExtractionResult:
    documents: int
    clauses: int
    references: int
    resolved: int
    unresolved: int
    output_root: Path


class ClauseReferenceRepository:
    """Persist reference analyses below a local, content-bearing workspace."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, analysis: ClauseReferenceAnalysis) -> Path:
        safe_id = analysis.clause_id.replace("/", "_").replace("\\", "_")
        return self._root / analysis.knowledge_domain / analysis.document_key / f"{safe_id}.yaml"

    def write(self, analysis: ClauseReferenceAnalysis) -> Path:
        path = self.path_for(analysis)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = analysis.model_dump(mode="json", exclude_none=True)
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return path

    def load_for_key(self, clause_key: str) -> ClauseReferenceAnalysis | None:
        try:
            domain, document, clause_id = clause_key.split(":", maxsplit=2)
        except ValueError:
            return None
        safe_id = clause_id.replace("/", "_").replace("\\", "_")
        path = self._root / domain / document / f"{safe_id}.yaml"
        if not path.exists():
            return None
        return ClauseReferenceAnalysis.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )


class ClauseReferenceExtractionService:
    """Extract and resolve same-document clause references deterministically."""

    def __init__(self, documents: EngineeringDocumentRepository) -> None:
        self._documents = documents

    def run(
        self,
        *,
        knowledge_domain: str,
        output_root: Path,
        document_keys: tuple[str, ...] = (),
        overwrite: bool = False,
    ) -> ReferenceExtractionResult:
        output = ClauseReferenceRepository(output_root)
        documents = tuple(
            document
            for document in self._documents.list()
            if not document_keys or document.key.value in document_keys
        )
        if document_keys:
            found = {document.key.value for document in documents}
            missing = sorted(set(document_keys) - found)
            if missing:
                raise ValueError(f"unknown EngineeringDocuments: {', '.join(missing)}")

        clause_count = reference_count = resolved_count = unresolved_count = 0
        for document in documents:
            resolver = _DocumentReferenceResolver(document)
            for clause in document.clauses:
                analysis = resolver.analyse(knowledge_domain, clause)
                path = output.path_for(analysis)
                if path.exists() and not overwrite:
                    continue
                output.write(analysis)
                clause_count += 1
                reference_count += len(analysis.references)
                for occurrence in analysis.references:
                    if occurrence.status is ReferenceResolutionStatus.RESOLVED:
                        resolved_count += 1
                    else:
                        unresolved_count += 1
        return ReferenceExtractionResult(
            documents=len(documents),
            clauses=clause_count,
            references=reference_count,
            resolved=resolved_count,
            unresolved=unresolved_count,
            output_root=output_root,
        )


class _DocumentReferenceResolver:
    def __init__(self, document: EngineeringDocument) -> None:
        self._document = document
        self._by_reference: dict[tuple[str | None, str], list[Clause]] = {}
        for clause in document.clauses:
            key = (clause.reference.part, _normalize_reference(clause.reference.clause))
            self._by_reference.setdefault(key, []).append(clause)
        self._ordered = tuple(document.clauses)
        self._position = {clause.id.value: index for index, clause in enumerate(self._ordered)}

    def analyse(self, knowledge_domain: str, clause: Clause) -> ClauseReferenceAnalysis:
        occurrences = tuple(self._extract(clause.plain_text, clause))
        return ClauseReferenceAnalysis(
            knowledge_domain=knowledge_domain,
            document_key=self._document.key.value,
            clause_id=clause.id.value,
            clause_reference=clause.reference.clause,
            clause_title=clause.heading,
            references=occurrences,
        )

    def _extract(self, text: str, source_clause: Clause):
        occupied: list[tuple[int, int]] = []
        for match in _RANGE_RE.finditer(text):
            occupied.append(match.span())
            yield self._resolve_range(match, source_clause)
        for match in _SINGLE_RE.finditer(text):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            # Bare decimal numbers are only references when they match a real clause.
            normalized = _normalize_reference(match.group("reference"))
            if (
                match.group("prefix") is None
                and (source_clause.reference.part, normalized) not in self._by_reference
            ):
                continue
            yield self._resolve_single(match, source_clause)

    def _resolve_single(
        self, match: re.Match[str], source_clause: Clause
    ) -> ClauseReferenceOccurrence:
        reference = match.group("reference")
        candidates = [
            c
            for c in self._by_reference.get(
                (source_clause.reference.part, _normalize_reference(reference)), ()
            )
            if c.id != source_clause.id
        ]
        if len(candidates) == 1:
            status = ReferenceResolutionStatus.RESOLVED
            unresolved: tuple[str, ...] = ()
        elif len(candidates) > 1:
            status = ReferenceResolutionStatus.AMBIGUOUS
            unresolved = (reference,)
        else:
            status = ReferenceResolutionStatus.UNRESOLVED
            unresolved = (reference,)
        return ClauseReferenceOccurrence(
            kind=ReferenceKind.CLAUSE,
            surface_text=match.group(0).strip(),
            start_offset=match.start(),
            end_offset=match.end(),
            reference=reference,
            status=status,
            targets=tuple(_target(candidate) for candidate in candidates),
            unresolved_references=unresolved,
        )

    def _resolve_range(
        self, match: re.Match[str], source_clause: Clause
    ) -> ClauseReferenceOccurrence:
        start_ref, end_ref = match.group("start"), match.group("end")
        starts = [
            c
            for c in self._by_reference.get(
                (source_clause.reference.part, _normalize_reference(start_ref)), ()
            )
            if c.id != source_clause.id
        ]
        ends = [
            c
            for c in self._by_reference.get(
                (source_clause.reference.part, _normalize_reference(end_ref)), ()
            )
            if c.id != source_clause.id
        ]
        targets: list[Clause] = []
        unresolved: list[str] = []
        if len(starts) == 1 and len(ends) == 1:
            start_index, end_index = (
                self._position[starts[0].id.value],
                self._position[ends[0].id.value],
            )
            if start_index <= end_index:
                targets = list(self._ordered[start_index : end_index + 1])
            else:
                unresolved.extend((start_ref, end_ref))
        else:
            if len(starts) != 1:
                unresolved.append(start_ref)
            if len(ends) != 1:
                unresolved.append(end_ref)
        if targets and not unresolved:
            status = ReferenceResolutionStatus.RESOLVED
        elif targets:
            status = ReferenceResolutionStatus.PARTIALLY_RESOLVED
        elif len(starts) > 1 or len(ends) > 1:
            status = ReferenceResolutionStatus.AMBIGUOUS
        else:
            status = ReferenceResolutionStatus.UNRESOLVED
        return ClauseReferenceOccurrence(
            kind=ReferenceKind.CLAUSE_RANGE,
            surface_text=match.group(0).strip(),
            start_offset=match.start(),
            end_offset=match.end(),
            range_start=start_ref,
            range_end=end_ref,
            status=status,
            targets=tuple(_target(candidate) for candidate in targets),
            unresolved_references=tuple(dict.fromkeys(unresolved)),
        )


def _target(clause: Clause) -> ResolvedReferenceTarget:
    return ResolvedReferenceTarget(
        clause_id=clause.id.value,
        reference=clause.reference.clause,
        heading=clause.heading,
    )


def _normalize_reference(value: str) -> str:
    return value.strip().rstrip(".,;:)").casefold()
