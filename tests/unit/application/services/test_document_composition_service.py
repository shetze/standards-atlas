from pathlib import Path

import pytest

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services.document_composition_service import (
    DocumentCompositionError,
)
from standards_atlas.cli.composition import build_document_composition_service
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


def _clause(identifier: str, text: str | None = None, *, volume: str = "1") -> Clause:
    content = (TextBlock(id=f"{identifier}-text", text=text),) if text is not None else ()
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="TEST", year=2026, clause=identifier, part=volume),
        clause_type=ClauseType.CLAUSE,
        content=content,
    )


def _document(key: str, *clauses: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.OTHER,
        clauses=clauses,
    )


def _part_document(key: str, *clauses: Clause, volume: str = "1") -> EngineeringDocument:
    root = Clause(
        id=ClauseId(value=f"{key}-root"),
        reference=StandardReference(standard="TEST", year=2026, clause="0", part=volume),
        clause_type=ClauseType.TOC,
        heading=f"Part {volume.replace('§', '-')}",
    )
    return _document(key, root, *clauses)


def test_compose_uses_part_order_and_includes_supplement_clauses(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(_document("FAMILY", _clause("legacy")))
    repository.save(_part_document("PART-1", _clause("A", "Content A")))
    repository.save(
        _part_document(
            "SUPPLEMENT",
            _clause("S", "Supplement content", volume="3§1"),
            volume="3§1",
        )
    )
    repository.save(_part_document("PART-2", _clause("B", "Content B", volume="2"), volume="2"))

    composed = build_document_composition_service(tmp_path).compose(
        "FAMILY", ("PART-1", "SUPPLEMENT", "PART-2")
    )

    assert [clause.reference.clause for clause in composed.clauses] == [
        "0",
        "A",
        "0",
        "S",
        "0",
        "B",
    ]
    assert [clause.heading for clause in composed.clauses[::2]] == [
        "Part 1",
        "Part 3-1",
        "Part 2",
    ]
    assert [clause.content[0].text for clause in composed.clauses[1::2]] == [
        "Content A",
        "Supplement content",
        "Content B",
    ]
    assert repository.exists(DocumentKey(value="FAMILY"))
    assert composed.key == DocumentKey(value="FAMILY")
    assert composed.part_keys == ("PART-1", "SUPPLEMENT", "PART-2")


def test_compose_creates_root_for_legacy_supplement_without_clause_zero(
    tmp_path: Path,
) -> None:
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(_document("IEC61508-3-1", _clause("S", "Supplement", volume="3§1")))

    composed = build_document_composition_service(tmp_path).compose("FAMILY", ("IEC61508-3-1",))

    root, clause = composed.clauses
    assert root.reference == StandardReference(standard="TEST", part="3§1", year=2026, clause="0")
    assert root.reference.part == "3§1"
    assert root.heading == "Part 3-1"
    assert root.clause_type is ClauseType.TOC
    assert clause.reference.clause == "S"


def test_compose_rejects_duplicate_clause_ids_across_parts(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(_part_document("PART-1", _clause("A", "First")))
    repository.save(_part_document("PART-2", _clause("A", "Second"), volume="2"))

    with pytest.raises(DocumentCompositionError, match="more than one part"):
        build_document_composition_service(tmp_path).compose("FAMILY", ("PART-1", "PART-2"))


def test_compose_rejects_multiple_clause_zero_roots(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    root_a = _part_document("PART-1").clauses[0]
    root_b = root_a.model_copy(update={"id": ClauseId(value="second-root")})
    repository.save(_document("PART-1", root_a, root_b, _clause("A", "Content")))

    with pytest.raises(DocumentCompositionError, match="at most one clause 0"):
        build_document_composition_service(tmp_path).compose("FAMILY", ("PART-1",))
