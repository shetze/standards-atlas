"""Translate extracted scope citations into canonical reaches without guessing IDs.

The provider describes a target and whether it includes descendants. It does not
construct ScopeReach or choose its mutually exclusive address fields. Document
and part targets are matched against the supplied physical-document catalogue;
clause coordinates use the same exact index as reference routing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from standards_atlas.application.references.resolution import (
    DocumentReferenceIndex,
    canonical_reference,
    reference_key,
)
from standards_atlas.domain.model import EngineeringDocument, ScopeReach, ScopeReachKind
from standards_atlas.shared.hashing import sha256_json

_CURRENT_DOCUMENT = {"this document", "current document", "this standard"}
_PARTS = re.compile(r"^parts?\s+(.+?)(?:\s+of\s+(.+))?$", re.I)
_UNLABELLED_PARTS = re.compile(r"^(\d[\d\s,\-&]*?(?:and\s+\d+)?)\s+of\s+(.+)$", re.I)


def _text_key(text: str) -> str:
    return " ".join(text.split()).casefold().rstrip(".;")


def _part_numbers(text: str) -> tuple[str, ...]:
    numbers: list[str] = []
    for member in re.split(r"\s*(?:,\s*(?:and\s+)?|\band\b|&)\s*", text.strip()):
        member = re.sub(r"^parts?\s+", "", member, flags=re.I)
        bounds = re.fullmatch(r"(\d+)\s*(?:to|through|–|—)\s*(\d+)", member, re.I)
        if bounds:
            lo, hi = map(int, bounds.groups())
            if hi < lo or hi - lo > 200:
                raise ValueError("part range must be ascending and contain at most 201 members")
            numbers.extend(str(number) for number in range(lo, hi + 1))
        elif re.fullmatch(r"\d+(?:-\d+)*", member):
            numbers.append(member)
        else:
            raise ValueError(f"unrecognized part coordinate: {member!r}")
    if not numbers or len(numbers) > 201:
        raise ValueError("scope part list must contain between 1 and 201 members")
    return tuple(dict.fromkeys(numbers))


@dataclass(frozen=True)
class _DocumentAddress:
    key: str
    standard: str
    part: str | None
    year: int | None

    @property
    def reference(self) -> str:
        name = self.standard + (f"-{self.part}" if self.part else "")
        return name + (f":{self.year}" if self.year is not None else "")

    @property
    def aliases(self) -> set[str]:
        name = self.standard + (f"-{self.part}" if self.part else "")
        return {reference_key(item) for item in (self.key, name, self.reference)}

    def matches_standard(self, text: str) -> bool:
        aliases = {reference_key(self.standard)}
        if self.year is not None:
            aliases.add(reference_key(f"{self.standard}:{self.year}"))
        return reference_key(text) in aliases


class ScopeTargetResolver:
    """Resolve scope citations against an explicit, edition-aware document set.

    Unknown clause coordinates stay explicitly unresolved; unknown or ambiguous
    whole-document/part targets are errors, not silently widened local scopes.
    Compound targets resolve atomically. No source sentence is reinterpreted as a
    scope declaration here: deciding that a scope exists remains the provider's job.
    """

    def __init__(
        self,
        document: EngineeringDocument,
        documents: Iterable[EngineeringDocument] = (),
    ) -> None:
        self.document = document
        self.documents = {item.key.value: item for item in documents}
        self.documents[document.key.value] = document
        self.addresses: list[_DocumentAddress] = []
        for key, item in sorted(self.documents.items()):
            namespaces = {
                (clause.reference.standard, clause.reference.part, clause.reference.year)
                for clause in item.clauses
            }
            # An aggregate is not a unique physical part. Never bind a part to it.
            if len(namespaces) == 1:
                standard, part, year = next(iter(namespaces))
                self.addresses.append(_DocumentAddress(key, standard, part, year))

    def catalog(self) -> list[dict[str, object]]:
        """Stable identity-only context; generated values cannot affect the input hash."""
        return [
            {
                "document_key": item.key,
                "reference": item.reference,
                "standard": item.standard,
                "part": item.part,
            }
            for item in self.addresses
        ]

    def fingerprint(self) -> str:
        """Include target structure, but never previously generated semantic outputs."""
        return sha256_json(
            [
                {
                    "document_key": key,
                    "clauses": [
                        (
                            clause.id.value,
                            clause.reference.model_dump(mode="json"),
                            clause.clause_type.value,
                        )
                        for clause in document.clauses
                    ],
                }
                for key, document in sorted(self.documents.items())
            ]
        )

    def resolve(
        self,
        reference: str,
        *,
        include_descendants: bool,
        source_clause_id: str,
        evidence: tuple[str, ...] = (),
    ) -> tuple[ScopeReach, ...]:
        text = reference.strip()
        if not text:
            raise ValueError("scope target reference must not be empty")
        if not isinstance(include_descendants, bool):
            raise ValueError("scope include_descendants must be a boolean")
        key = reference_key(text)
        if key in _CURRENT_DOCUMENT:
            return (ScopeReach(kind=ScopeReachKind.DOCUMENT, document_key=self.document.key.value),)
        source = next(
            (clause for clause in self.document.clauses if clause.id.value == source_clause_id),
            None,
        )
        if source is None:
            raise ValueError(f"scope source clause not found: {source_clause_id}")
        if key == "this part":
            if source.reference.part is None:
                raise ValueError("'this part' has no uniquely identified source part")
            text = f"Part {source.reference.part} of {source.reference.standard}"
            if source.reference.year is not None:
                text += f":{source.reference.year}"

        match = _PARTS.fullmatch(text)
        if match is None:
            # '1, 2, 3 and 4 of IEC 61508' alone could also denote clauses.
            # Accept the omitted label only when a source-verified quotation
            # explicitly identifies the *same* list as parts.
            unlabelled = _UNLABELLED_PARTS.fullmatch(text)
            source_text = _text_key(source.plain_text)
            if unlabelled and any(
                _text_key(quote) in source_text
                and re.search(
                    r"\bparts?\s+" + re.escape(_text_key(text)) + r"(?=$|[\s,.;)])",
                    _text_key(quote),
                )
                for quote in evidence
                if quote.strip()
            ):
                match = _PARTS.fullmatch("Parts " + text)
        if match is not None:
            numbers = _part_numbers(match.group(1))
            standard = match.group(2) or source.reference.standard
            reaches = []
            for part in numbers:
                addresses = [
                    item
                    for item in self.addresses
                    if item.part == part and item.matches_standard(standard)
                ]
                if len(addresses) != 1:
                    raise ValueError(
                        f"Part {part} of {standard} needs exactly one physical document; "
                        f"found {len(addresses)}. Use a catalogued edition; "
                        "do not substitute the source document or drop list members."
                    )
                reaches.append(
                    ScopeReach(
                        kind=ScopeReachKind.PART, document_key=addresses[0].key, part=f"Part {part}"
                    )
                )
            return tuple(reaches)

        addresses = [item for item in self.addresses if key in item.aliases]
        if addresses:
            if len(addresses) != 1:
                raise ValueError(f"ambiguous scope document {text!r}; specify its edition")
            return (ScopeReach(kind=ScopeReachKind.DOCUMENT, document_key=addresses[0].key),)

        # Qualified citations may target another loaded document; bare coordinates
        # are always resolved within the source namespace, never globally.
        qualified = [
            item
            for item in self.addresses
            if any(
                key.startswith(alias + " ") or key.endswith(" of " + alias)
                for alias in item.aliases
            )
        ]
        if len(qualified) > 1:
            raise ValueError(f"ambiguous scope citation {text!r}; specify its edition")
        target_document = self.document
        target_text = text
        if qualified:
            address = qualified[0]
            target_document = self.documents[address.key]
            prefixes = [alias for alias in address.aliases if key.startswith(alias + " ")]
            if prefixes:
                alias = max(prefixes, key=len)
                target_text = key[len(alias) + 1 :]
            else:
                alias = max(
                    (alias for alias in address.aliases if key.endswith(" of " + alias)), key=len
                )
                target_text = key[: -len(" of " + alias)]
        index = DocumentReferenceIndex(target_document)
        target_source = (
            source_clause_id
            if target_document.key == self.document.key
            else target_document.clauses[0].id.value
        )
        result = index.resolve_group(target_text, target_source)
        kind = ScopeReachKind.SUBTREE if include_descendants else ScopeReachKind.CLAUSE
        if result.status == "resolved":
            return tuple(
                ScopeReach(
                    kind=kind,
                    document_key=target_document.key.value,
                    clause_id=clause.id.value,
                    reference=canonical_reference(clause),
                )
                for clause in result.targets
            )
        if index.coordinates(target_text):
            # A recognized clause/table/figure citation can lack a TOC identity.
            # That is an unresolved address, not an invalid model response. Keep
            # the complete literal group and its document; never substitute a
            # numeric clause, containing clause, or document-wide reach.
            return (ScopeReach(kind=kind, document_key=target_document.key.value, reference=text),)
        raise ValueError(
            f"cannot identify scope target {reference!r}. Use 'this document', "
            "a catalogued document, 'Part(s) ... of <standard>', or an exact clause, table "
            "or figure citation (including complete lists/ranges). "
            "Do not remove meaningful target text just to satisfy the schema."
        )
