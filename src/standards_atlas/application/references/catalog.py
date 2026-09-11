"""Exact reference targets in an explicit catalogue of physical documents."""

from __future__ import annotations

from collections.abc import Iterable

from standards_atlas.application.references.resolution import (
    DocumentReferenceIndex,
    canonical_reference,
    reference_key,
)
from standards_atlas.application.references.syntax import strip_document_qualifier
from standards_atlas.domain.model import EngineeringDocument, ReferenceTarget


class ReferenceDocumentCatalog:
    """Resolve complete citation groups, never guess an edition or a missing ID.

    Unlike a scope resolver this returns reference addresses only. An unknown
    external citation is valid evidence and stays literal, with no local ID.
    """

    def __init__(
        self, document: EngineeringDocument, documents: Iterable[EngineeringDocument] = ()
    ) -> None:
        self.document = document
        self.documents = {item.key.value: item for item in documents}
        self.documents[document.key.value] = document
        self._indexes: dict[str, DocumentReferenceIndex] = {}
        self.aliases: dict[str, set[str]] = {}
        for key, item in self.documents.items():
            namespaces = {
                (clause.reference.standard, clause.reference.part, clause.reference.year)
                for clause in item.clauses
            }
            if len(namespaces) != 1:
                continue  # An aggregate must not compete with its physical parts.
            standard, part, year = next(iter(namespaces))
            name = standard + (f"-{part}" if part else "")
            aliases = {reference_key(name), reference_key(key)}
            if year is not None:
                aliases.add(reference_key(f"{name}:{year}"))
            self.aliases[key] = aliases

    def targets(self, text: str, source_clause_id: str) -> tuple[ReferenceTarget, ...]:
        key = reference_key(text)
        matches = {
            document_key: max(aliases, key=len)
            for document_key, all_aliases in self.aliases.items()
            if (
                aliases := [
                    alias
                    for alias in all_aliases
                    if strip_document_qualifier(key, alias) is not None
                ]
            )
        }
        if len(matches) > 1:
            return (ReferenceTarget(reference=text),)
        document = self.document
        coordinate = text
        if matches:
            document_key, alias = next(iter(matches.items()))
            document = self.documents[document_key]
            coordinate = strip_document_qualifier(key, alias)
            assert coordinate is not None
        if document.key.value not in self._indexes:
            self._indexes[document.key.value] = DocumentReferenceIndex(document)
        index = self._indexes[document.key.value]
        # The local index rejects foreign designations rather than interpreting
        # their numeric components as local coordinates.
        source = (
            source_clause_id
            if document.key == self.document.key
            else document.clauses[0].id.value
            if document.clauses
            else ""
        )
        result = index.resolve_group(coordinate, source)
        if result.status == "resolved":
            return tuple(
                ReferenceTarget(
                    document_key=document.key.value,
                    clause_id=clause.id.value,
                    reference=canonical_reference(clause),
                    title=clause.heading,
                )
                for clause in result.targets
            )
        local_coordinate = bool(index.coordinates(coordinate))
        return (
            ReferenceTarget(
                document_key=document.key.value if matches or local_coordinate else None,
                reference=text,
            ),
        )
