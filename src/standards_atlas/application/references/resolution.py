"""Exact document-coordinate resolution, independent of provider-supplied IDs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from standards_atlas.domain.model import Clause, ClauseType, EngineeringDocument

_COORDINATE = r"(?:\d+(?:\.\d+)*[a-z]?|[a-z](?:\.\d+)*)"
_SINGLE = re.compile(rf"{_COORDINATE}\Z", re.I)
_PREFIX = re.compile(
    r"^(clauses?|subclauses?|sections?|paragraphs?|annex(?:es)?|appendi(?:x|ces)|"
    r"tables?|figures?|figs?\.?)\s+",
    re.I,
)
_SELF = {"this clause", "this subclause", "this section"}
_STANDARD = re.compile(r"\b(?:IEC|ISO|EN|DIN|BS|IEEE)(?:[/ -](?:IEC|ISO|EN))*\s*\d", re.I)


def reference_key(value: str) -> str:
    key = " ".join(value.strip().rstrip(".,;:)").split()).casefold()
    return re.sub(r"\b(iec|iso|en|din|bs|ieee)\s*(?=\d)", r"\1 ", key)


def _object_prefix(prefix: str) -> str:
    """Keep labelled objects out of the numeric clause namespace."""
    if prefix.casefold().startswith("table"):
        return "table "
    if prefix.casefold().startswith("fig"):
        return "figure "
    return ""


def _namespace(clause: Clause) -> tuple[str, str | None, int | None]:
    ref = clause.reference
    return reference_key(ref.standard), ref.part, ref.year


def canonical_reference(clause: Clause) -> str:
    """Keep table coordinates distinct even when the stored number omits its prefix."""
    reference = clause.reference
    if clause.clause_type == ClauseType.TABLE and not reference_key(reference.clause).startswith(
        "table "
    ):
        reference = reference.model_copy(update={"clause": f"Table {reference.clause}"})
    return reference.as_text()


def _aliases(clause: Clause) -> set[str]:
    coordinate = reference_key(clause.reference.clause)
    match = _PREFIX.match(coordinate)
    kind = _object_prefix(match.group(1)) if match else ""
    if match:
        coordinate = coordinate[match.end() :]
    if clause.clause_type == ClauseType.TABLE:
        kind = "table "
    if kind:
        return {f"{kind}{coordinate}"}
    if not _SINGLE.fullmatch(coordinate):
        return {reference_key(clause.reference.clause)}
    aliases = {coordinate}
    aliases.update(f"{prefix} {coordinate}" for prefix in ("clause", "subclause", "section"))
    if coordinate[0].isalpha():
        aliases.update(f"{prefix} {coordinate}" for prefix in ("annex", "appendix"))
    return aliases


@dataclass(frozen=True)
class ReferenceResolution:
    """A group is resolved only when *every* coordinate is uniquely addressable."""

    targets: tuple[Clause, ...] = ()
    status: str = "unresolved"


class DocumentReferenceIndex:
    """A bounded TOC index: no prefix/ancestor matching and no guessed target IDs."""

    def __init__(self, document: EngineeringDocument) -> None:
        self.document_key = document.key.value
        self.clauses = {clause.id.value: clause for clause in document.clauses}
        self.unqualified: dict[str, dict[str, Clause]] = {}
        self.qualified: dict[str, dict[str, Clause]] = {}
        self.prefixes: set[str] = set()
        for clause in document.clauses:
            ref = clause.reference
            standard = f"{ref.standard}-{ref.part}" if ref.part else ref.standard
            prefixes = {reference_key(standard)}
            if ref.year is not None:
                prefixes.add(reference_key(f"{standard}:{ref.year}"))
            self.prefixes.update(prefixes)
            for alias in _aliases(clause):
                self.unqualified.setdefault(alias, {})[clause.id.value] = clause
                for prefix in prefixes:
                    self.qualified.setdefault(f"{prefix} {alias}", {})[clause.id.value] = clause

    def _candidates(self, text: str, source_clause_id: str) -> tuple[Clause, ...]:
        key = reference_key(text)
        source = self.clauses.get(source_clause_id)
        if key in _SELF:
            return (source,) if source else ()
        if key in self.qualified:
            return tuple(self.qualified[key].values())
        if source is None:
            return ()
        return tuple(
            clause
            for clause in self.unqualified.get(key, {}).values()
            if _namespace(clause) == _namespace(source)
        )

    def resolve(self, text: str, source_clause_id: str) -> Clause | None:
        candidates = self._candidates(text, source_clause_id)
        return candidates[0] if len(candidates) == 1 else None

    def coordinates(self, text: str) -> tuple[str, ...]:
        """Parse a whole citation or bounded list/range, never a substring of it."""
        key = reference_key(text)
        standard = ""
        for prefix in sorted(self.prefixes, key=len, reverse=True):
            if key.startswith(prefix + " "):
                standard, key = prefix + " ", key[len(prefix) + 1 :]
                break
        # A foreign edition/part must never fall through to local bare coordinates.
        if not standard and _STANDARD.search(key):
            return ()
        if key in _SELF:
            return (key,)
        match = _PREFIX.match(key)
        kind = ""
        if match:
            prefix = match.group(1)
            kind = _object_prefix(prefix)
            key = key[match.end() :]
        # Accept repeated prefixes ("Annex G and Annex H") and shared prefixes.
        members = re.split(r"\s*(?:,\s*(?:and\s+)?|\band\b|&)\s*", key)
        result: list[str] = []
        for member in members:
            member_prefix = _PREFIX.match(member)
            if member_prefix:
                # In "Figure 2, Table 1 and 3", the last member is Table 3,
                # not Figure 3 or Clause 3. A repeated label changes inheritance.
                kind = _object_prefix(member_prefix.group(1))
                member = member[member_prefix.end() :].strip()
            member_kind = kind
            bounds = re.fullmatch(
                rf"({_COORDINATE})\s*(?:to|through|–|—|-)\s*({_COORDINATE})", member, re.I
            )
            if bounds:
                first, last = bounds.groups()
                start, _, a = first.rpartition(".")
                end, _, b = last.rpartition(".")
                if start != end or not a.isdigit() or not b.isdigit():
                    return ()
                lo, hi = int(a), int(b)
                if hi < lo or hi - lo > 200:
                    return ()
                coordinates = [f"{start + '.' if start else ''}{n}" for n in range(lo, hi + 1)]
            elif _SINGLE.fullmatch(member):
                coordinates = [member]
            else:
                return ()
            result.extend(f"{standard}{member_kind}{coordinate}" for coordinate in coordinates)
        return tuple(dict.fromkeys(result))

    def resolve_group(self, text: str, source_clause_id: str) -> ReferenceResolution:
        coordinates = self.coordinates(text)
        if not coordinates:
            # Named non-numeric TOC entries still require exact equality.
            coordinates = (text,)
        targets: dict[str, Clause] = {}
        ambiguous = False
        missing = False
        for coordinate in coordinates:
            candidates = self._candidates(coordinate, source_clause_id)
            if len(candidates) == 1:
                targets[candidates[0].id.value] = candidates[0]
            elif candidates:
                ambiguous = True
            else:
                missing = True
        status = (
            "ambiguous"
            if ambiguous
            else "partially_resolved"
            if missing and targets
            else "unresolved"
            if missing
            else "resolved"
        )
        return ReferenceResolution(tuple(targets.values()), status)
