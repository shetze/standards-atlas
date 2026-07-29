"""Generate AtlasData skeletons from one or more Docling JSON documents."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from standards_atlas.adapters.atlasdata.metadata import (
    AtlasDataLifecycleStatus,
    parse_metadata,
)
from standards_atlas.application.services.semantic_classifier import (
    SemanticClassificationContext,
    SemanticClassifier,
)
from standards_atlas.domain.model.semantic_classification import (
    DocumentStructure,
    NormativeStatus,
    StatementFunction,
)

_NUMERIC_HEADING = re.compile(
    r"^(?P<reference>0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*)"
    r"(?:[\t ]+(?P<title>.+))?$"
)
_NUMERIC_REFERENCE_ONLY = re.compile(r"^(?:0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*)$")
_ANNEX_HEADING = re.compile(
    r"^Annex\s+(?P<letter>[A-Z])"
    r"(?:\s*\((?P<status>normative|informative)\))?"
    r"(?:[\t ]+(?P<title>.+))?$",
    re.IGNORECASE,
)
_ANNEX_CLAUSE_HEADING = re.compile(r"^(?P<reference>[A-Z](?:\.\d+)+)(?:[\t ]+(?P<title>.+))?$")
_REFERENCE_ONLY = re.compile(r"^(?:0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*|[A-Z](?:\.\d+)*)$")
_PART_SPEC = re.compile(r"^(?P<part>[1-9]\d*(?:-[1-9]\d*)?)=(?P<path>.+)$")


class AtlasDataOnboardingError(RuntimeError):
    """Raised when an AtlasData skeleton cannot be generated."""


@dataclass(frozen=True)
class DoclingPartSource:
    """Explicit association between a standard part and Docling JSON."""

    part: str
    path: Path

    def __post_init__(self) -> None:
        # Keep compatibility with callers that still construct the source with an int.
        object.__setattr__(self, "part", str(self.part))

    @classmethod
    def parse(cls, value: str) -> DoclingPartSource:
        match = _PART_SPEC.fullmatch(value.strip())
        if match is None:
            raise AtlasDataOnboardingError(
                f"Invalid part source '{value}'. Expected PART=PATH, for example 1=document.json."
            )
        return cls(part=match.group("part"), path=Path(match.group("path")))


@dataclass(frozen=True)
class DiscoveredClause:
    """One public clause reference and heading discovered in Docling JSON."""

    reference: str
    title: str
    type_marker: str
    source_item_ids: tuple[str, ...]
    annex_status: str | None = None


@dataclass(frozen=True)
class DiscoveredPart:
    """All clauses discovered for one explicitly identified standard part."""

    part: str
    source: Path
    clauses: tuple[DiscoveredClause, ...]


@dataclass(frozen=True)
class AtlasDataOnboardingResult:
    """Result of generating one AtlasData source file."""

    output: Path
    standard_name: str
    year: int
    parts: tuple[DiscoveredPart, ...]

    @property
    def clauses(self) -> tuple[DiscoveredClause, ...]:
        return tuple(clause for part in self.parts for clause in part.clauses)


def _detect_part_from_metadata(value: str, publication_year: int) -> str | None:
    """Return a declared part or part-supplement identifier from metadata.

    Edition markers and publication years are deliberately ignored. A designation
    such as ``IEC 61508-3-1`` is interpreted as part ``3`` with supplement ``1``.
    """
    explicit = re.search(
        r"\bpart\s*[-_:]?\s*(?P<part>[1-9]\d*(?:-[1-9]\d*)?)\b",
        value,
        re.IGNORECASE,
    )
    if explicit:
        return explicit.group("part")

    normalized = value.replace("+", "-")
    # A trailing publication year belongs to the edition, not to the part
    # identifier. Strip it before recognizing optional supplement suffixes.
    normalized = re.sub(
        rf"[-_]{publication_year}(?=(?:\.[A-Za-z0-9]+)?$)",
        "",
        normalized,
    )
    designation = re.search(
        r"(?<!\d)\d{4,6}-(?P<part>[1-9]\d*)"
        r"(?:-(?P<supplement>[1-9]\d*))?",
        normalized,
    )
    if designation:
        part = designation.group("part")
        supplement = designation.group("supplement")
        return f"{part}-{supplement}" if supplement else part

    numbers = [int(token) for token in re.findall(r"(?<!\d)\d+(?!\d)", normalized)]
    candidates = [number for number in numbers if number != publication_year]
    if len(candidates) >= 2:
        return str(candidates[-1])
    return None


class AtlasDataOnboardingService:
    """Create a public AtlasData structure from Docling section headings."""

    def __init__(self, role_classifier: SemanticClassifier | None = None) -> None:
        self._role_classifier = role_classifier or SemanticClassifier()

    def generate(
        self,
        source: Path,
        output: Path,
        *,
        standard_name: str,
        year: int,
        digits: int = 8,
        parent: str | None = None,
        overwrite: bool = False,
    ) -> AtlasDataOnboardingResult:
        """Backward-compatible onboarding for a single-part standard."""
        return self.generate_parts(
            (DoclingPartSource(part="1", path=source),),
            output,
            standard_name=standard_name,
            year=year,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
            include_part_context=False,
        )

    def generate_parts(
        self,
        sources: Sequence[DoclingPartSource],
        output: Path,
        *,
        standard_name: str,
        year: int,
        digits: int = 8,
        parent: str | None = None,
        overwrite: bool = False,
        include_part_context: bool = True,
    ) -> AtlasDataOnboardingResult:
        if output.exists():
            if not overwrite:
                raise AtlasDataOnboardingError(
                    f"AtlasData output already exists: {output}. Use --overwrite to replace it."
                )
            try:
                status = parse_metadata(output.read_text(encoding="utf-8")).lifecycle_status
            except ValueError as exc:
                raise AtlasDataOnboardingError(
                    f"Cannot determine lifecycle status of existing AtlasData file: {output}"
                ) from exc
            if status is not AtlasDataLifecycleStatus.PROPOSED:
                raise AtlasDataOnboardingError(
                    f"AtlasData file {output} is {status.value} and cannot be overwritten. "
                    "Only proposed files may be regenerated."
                )
        if not sources:
            raise AtlasDataOnboardingError("At least one Docling part source is required.")

        part_numbers = [source.part for source in sources]
        duplicates = sorted({part for part in part_numbers if part_numbers.count(part) > 1})
        if duplicates:
            raise AtlasDataOnboardingError(
                "Duplicate part assignments: " + ", ".join(str(part) for part in duplicates)
            )

        parts: list[DiscoveredPart] = []
        for source in sorted(sources, key=lambda value: value.part):
            if not source.path.is_file():
                raise AtlasDataOnboardingError(f"Docling source does not exist: {source.path}")
            document = json.loads(source.path.read_text(encoding="utf-8"))
            if include_part_context:
                self._validate_part_metadata(document, source, publication_year=year)
            clauses = self.discover_clauses(document)
            if not clauses:
                raise AtlasDataOnboardingError(
                    f"No numbered clause or annex headings found in Docling document: {source.path}"
                )
            parts.append(DiscoveredPart(source.part, source.path, clauses))

        result_parts = tuple(parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            self.render(
                standard_name=standard_name,
                year=year,
                digits=digits,
                parent=parent,
                parts=result_parts,
                include_part_context=include_part_context,
            ),
            encoding="utf-8",
        )
        return AtlasDataOnboardingResult(output, standard_name, year, result_parts)

    def _validate_part_metadata(
        self,
        document: dict[str, Any],
        source: DoclingPartSource,
        *,
        publication_year: int,
    ) -> None:
        values = [
            str(document.get("name", "")),
            str(document.get("origin", {}).get("filename", "")),
        ]
        detected = {
            part
            for value in values
            if (part := _detect_part_from_metadata(value, publication_year)) is not None
        }
        if len(detected) == 1 and source.part not in detected:
            actual = next(iter(detected))
            raise AtlasDataOnboardingError(
                f"Part assignment {source.part} conflicts with Docling metadata "
                f"indicating part {actual}: {source.path}"
            )

    def discover_clauses(self, document: dict[str, Any]) -> tuple[DiscoveredClause, ...]:
        texts = document.get("texts")
        if not isinstance(texts, list):
            raise AtlasDataOnboardingError("Docling document has no 'texts' list.")

        headings = [item for item in texts if item.get("label") == "section_header"]
        discovered: dict[str, DiscoveredClause] = {}
        index = 0
        while index < len(headings):
            item = headings[index]
            text = _normalize_heading(item.get("text", ""))
            parsed = _parse_heading(text)
            if parsed is None:
                index += 1
                continue

            reference, title, annex_status = parsed
            source_ids = [str(item.get("self_ref", ""))]
            if not title and index + 1 < len(headings):
                next_item = headings[index + 1]
                next_text = _normalize_heading(next_item.get("text", ""))
                if (
                    next_text
                    and not _REFERENCE_ONLY.fullmatch(next_text)
                    and not _parse_heading(next_text)
                ):
                    title = next_text
                    source_ids.append(str(next_item.get("self_ref", "")))
                    index += 1

            title = title or _default_heading(reference, annex_status)
            candidate = DiscoveredClause(
                reference=reference,
                title=title,
                type_marker="u",
                source_item_ids=tuple(source_ids),
                annex_status=annex_status,
            )
            existing = discovered.get(reference)
            if existing is None or _candidate_quality(candidate) > _candidate_quality(existing):
                discovered[reference] = candidate
            index += 1

        ordered = sorted(
            discovered.values(), key=lambda clause: _reference_sort_key(clause.reference)
        )
        classified: list[DiscoveredClause] = []
        for clause in ordered:
            classified.append(
                DiscoveredClause(
                    reference=clause.reference,
                    title=clause.title,
                    type_marker=_atlasdata_marker(
                        self._role_classifier.classify(
                            SemanticClassificationContext(
                                reference=clause.reference,
                                heading=clause.title,
                                ancestor_structures=_ancestor_structures(
                                    clause.reference, classified, self._role_classifier
                                ),
                                annex_status=(clause.annex_status or NormativeStatus.UNSPECIFIED),
                            )
                        ).classification,
                        clause.title,
                    ),
                    source_item_ids=clause.source_item_ids,
                    annex_status=clause.annex_status,
                )
            )
        return tuple(classified)

    def render(
        self,
        *,
        standard_name: str,
        year: int,
        digits: int,
        parent: str | None,
        parts: tuple[DiscoveredPart, ...],
        include_part_context: bool,
    ) -> str:
        metadata = ["# SPDX-License-Identifier: LGPL-3.0-only"]
        if parent:
            metadata.append(f'parent="{parent}"')
        part_digits = len(str(max(part.part for part in parts))) if include_part_context else 0
        metadata.extend(
            [
                f"digits={digits}",
                "partShift=0",
                f"partDigits={part_digits}",
                f'name="{standard_name}"',
                f"oyr={year}",
                'lifecycle_status="proposed"',
                "",
                "structure=(",
            ]
        )
        for part in parts:
            tokens = _render_structure_tokens(
                part.clauses, part.part if include_part_context else None
            )
            if include_part_context:
                tokens = [f"{part.part}-0", *tokens]
            metadata.append(' "' + " ".join([str(year), *tokens]) + '"')
        metadata.extend(
            [
                ")",
                "",
                "return 0;",
                "####",
                "# Public structural metadata generated from private Docling extractions.",
                "# Clause text is intentionally not included.",
                "####",
                "#---data---#",
            ]
        )

        for part in parts:
            standard_ref = (
                f"{standard_name}-{part.part}:{year}"
                if include_part_context
                else f"{standard_name}:{year}"
            )
            if include_part_context:
                root_reference = f"{standard_ref} 0"
                root_digest = hashlib.md5(f"toc|{root_reference}".encode()).hexdigest()
                metadata.append(
                    ";".join(["TOC", root_digest, root_reference, f"Part {part.part}", "u"])
                )
            for clause in part.clauses:
                standard_ref = (
                    f"{standard_name}-{part.part}:{year}"
                    if include_part_context
                    else f"{standard_name}:{year}"
                )
                full_reference = f"{standard_ref} {clause.reference}"
                digest = hashlib.md5(f"toc|{full_reference}".encode()).hexdigest()
                metadata.append(
                    ";".join(
                        [
                            "TOC",
                            digest,
                            full_reference,
                            _sanitize_field(clause.title),
                            clause.type_marker,
                        ]
                    )
                )
        return "\n".join(metadata) + "\n"


def _parse_heading(text: str) -> tuple[str, str, str | None] | None:
    annex = _ANNEX_HEADING.fullmatch(text)
    if annex is not None:
        letter = annex.group("letter").upper()
        status = annex.group("status")
        suffix = (annex.group("title") or "").strip()
        title = f"Annex {letter}"
        if status:
            status = status.lower()
            title += f" ({status})"
        if suffix:
            title += f" {suffix}"
        return letter, title, status

    annex_clause = _ANNEX_CLAUSE_HEADING.fullmatch(text)
    if annex_clause is not None:
        return annex_clause.group("reference"), (annex_clause.group("title") or "").strip(), None

    numeric = _NUMERIC_HEADING.fullmatch(text)
    if numeric is not None:
        return numeric.group("reference"), (numeric.group("title") or "").strip(), None
    return None


def _candidate_quality(clause: DiscoveredClause) -> tuple[int, int, int]:
    return (
        int(clause.annex_status is not None),
        int(clause.title not in {"Heading", f"Annex {clause.reference}"}),
        len(clause.title),
    )


def _normalize_heading(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _default_heading(reference: str, annex_status: str | None = None) -> str:
    if len(reference) == 1 and reference.isalpha():
        suffix = f" ({annex_status})" if annex_status else ""
        return f"Annex {reference}{suffix}"
    if reference == "1":
        return "Scope"
    if reference == "2":
        return "Normative references"
    if reference == "3":
        return "Terms and definitions"
    return "Heading"


def _atlasdata_marker(classification, heading: str) -> str:
    structure = classification.document_structure
    if structure is not None:
        if structure.category is DocumentStructure.SCOPE:
            return "s"
        if structure.category is DocumentStructure.TERMINOLOGY:
            return "t"
    normalized_heading = heading.strip().lower()
    if "objective" in normalized_heading:
        return "o"
    if "requirement" in normalized_heading:
        return "r"
    if StatementFunction.DEFINITION in classification.statement_functions:
        return "t"
    if StatementFunction.DESCRIPTION in classification.statement_functions:
        return "o"
    if StatementFunction.REQUIREMENT in classification.statement_functions:
        return "r"
    return "u"


def _ancestor_headings(reference: str, discovered: list[DiscoveredClause]) -> tuple[str, ...]:
    return tuple(
        clause.title for clause in discovered if _is_descendant(reference, clause.reference)
    )


def _ancestor_structures(
    reference: str,
    discovered: list[DiscoveredClause],
    classifier: SemanticClassifier,
) -> tuple[DocumentStructure, ...]:
    structures: list[DocumentStructure] = []
    for clause in discovered:
        if not _is_descendant(reference, clause.reference):
            continue
        classification = classifier.classify_deterministically(
            SemanticClassificationContext(reference=clause.reference, heading=clause.title)
        )
        structure = classification.classification.document_structure
        if structure is not None:
            structures.append(structure.category)
    return tuple(dict.fromkeys(structures))


def _is_descendant(reference: str, parent: str) -> bool:
    return reference.startswith(parent + ".")


def _reference_sort_key(reference: str) -> tuple[int, tuple[int, ...], str]:
    first = reference.split(".", 1)[0]
    if first.isdigit():
        return (0, tuple(int(part) for part in reference.split(".")), "")
    parts = reference.split(".")
    return (1, (ord(parts[0]), *(int(part) for part in parts[1:])), "")


def _render_structure_tokens(clauses: tuple[DiscoveredClause, ...], part: str | None) -> list[str]:
    numeric = tuple(clause for clause in clauses if clause.reference[0].isdigit())
    annexes = tuple(clause for clause in clauses if clause.reference[0].isalpha())
    rendered = _compress_structure_tokens(numeric)

    top_level_numbers = [int(clause.reference) for clause in numeric if clause.reference.isdigit()]
    annex_anchor_base = max(top_level_numbers, default=0)
    annex_letters = sorted({clause.reference.split(".")[0] for clause in annexes})
    anchor_by_letter = {
        letter: annex_anchor_base + index + 1 for index, letter in enumerate(annex_letters)
    }
    for clause in annexes:
        letter, *suffix = clause.reference.split(".")
        visible = letter + ("." + ".".join(suffix) if suffix else "")
        prefix = clause.type_marker if clause.type_marker in {"r", "s", "t", "o", "c", "m"} else ""
        rendered.append(f"{prefix}{anchor_by_letter[letter]}:{visible}")

    if part is not None:
        return [f"{part}-{token}" for token in rendered]
    return rendered


def _structure_token(clause: DiscoveredClause) -> str:
    prefix = clause.type_marker if clause.type_marker in {"r", "s", "t", "o", "c", "m"} else ""
    return prefix + clause.reference


def _compress_structure_tokens(clauses: tuple[DiscoveredClause, ...]) -> list[str]:
    tokens = [_structure_token(clause) for clause in clauses]
    compressed: list[str] = []
    index = 0
    while index < len(tokens):
        parsed = _parse_compressible_token(tokens[index])
        if parsed is None:
            compressed.append(tokens[index])
            index += 1
            continue
        type_prefix, parent, start = parsed
        end = start
        next_index = index + 1
        while next_index < len(tokens):
            candidate = _parse_compressible_token(tokens[next_index])
            if candidate != (type_prefix, parent, end + 1):
                break
            end += 1
            next_index += 1
        if end > start:
            stem = f"{parent}." if parent else ""
            compressed.append(f"{type_prefix}{stem}{{{start}..{end}}}")
        else:
            compressed.append(tokens[index])
        index = next_index
    return compressed


def _parse_compressible_token(token: str) -> tuple[str, str, int] | None:
    match = re.fullmatch(r"(?P<type>[a-z]?)(?P<reference>\d+(?:\.\d+)*)", token)
    if match is None:
        return None
    parts = match.group("reference").split(".")
    return match.group("type"), ".".join(parts[:-1]), int(parts[-1])


def _sanitize_field(value: str) -> str:
    return value.replace(";", ",").replace("\n", " ").strip()
