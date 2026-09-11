"""Private address diagnostics, independent of semantic validity and run status."""

from __future__ import annotations

import re
from collections.abc import Iterable

from standards_atlas.application.references.catalog import ReferenceDocumentCatalog
from standards_atlas.application.references.resolution import DocumentReferenceIndex, reference_key
from standards_atlas.application.references.syntax import strip_document_qualifier
from standards_atlas.domain.model import EngineeringDocument

TARGET_DIAGNOSTICS_CONTRACT = "context-target-diagnostics-v1"
_STANDARD = re.compile(
    r"\b(?:IEC|ISO|EN|DIN|BS|IEEE)(?:[/ -](?:IEC|ISO|EN))*\s*\d+(?:-\d+)*(?::\d{4})?",
    re.I,
)
_OBJECT = re.compile(r"\b(?:tables?|figures?|figs?\.?)\s+", re.I)


class TargetDiagnostics:
    """Classify a missing clause ID without assigning an ID or judging its role."""

    def __init__(
        self, document: EngineeringDocument, documents: Iterable[EngineeringDocument] = ()
    ) -> None:
        self.catalog = ReferenceDocumentCatalog(document, documents)
        self.document = document
        self.indexes: dict[str, DocumentReferenceIndex] = {}

    def reason(self, reference: str | None, document_key: str | None, source_clause_id: str) -> str:
        key = reference_key(reference or "")
        aliases = self.catalog.aliases
        whole = {name for name, names in aliases.items() if key in names}
        qualified = {
            name: max(matches, key=len)
            for name, names in aliases.items()
            if (
                matches := [
                    alias for alias in names if strip_document_qualifier(key, alias) is not None
                ]
            )
        }
        matched = whole or set(qualified)
        if len(matched) > 1:
            return "ambiguous_address"
        if matched and document_key is not None and document_key not in matched:
            return "document_key_mismatch"
        if whole:
            return "document_reference"
        standards = tuple(_STANDARD.finditer(key))
        if not matched and standards:
            # An explicitly different edition is not the available edition.
            for standard in standards:
                name = standard.group(0)
                base = re.sub(r":\d{4}$", "", name)
                if name != base and any(base in names for names in aliases.values()):
                    return "edition_mismatch"
            return "target_document_not_loaded"
        target_key = next(iter(matched), document_key or self.document.key.value)
        target = self.catalog.documents.get(target_key)
        if target is None:
            return "target_document_not_loaded"
        coordinate = key
        if qualified:
            alias = qualified[target_key]
            coordinate = strip_document_qualifier(key, alias)
            assert coordinate is not None
        if target_key not in self.indexes:
            self.indexes[target_key] = DocumentReferenceIndex(target)
        source = (
            source_clause_id
            if target_key == self.document.key.value
            else target.clauses[0].id.value
            if target.clauses
            else ""
        )
        result = self.indexes[target_key].resolve_group(coordinate, source)
        if result.status == "ambiguous":
            return "ambiguous_address"
        if result.status == "resolved":
            return "addressable_clause"
        if _OBJECT.search(coordinate):
            return "object_not_indexed"
        return "unresolved_clause"
