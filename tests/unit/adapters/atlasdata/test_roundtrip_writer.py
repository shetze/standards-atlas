from pathlib import Path

from standards_atlas.adapters.atlasdata.roundtrip_writer import AtlasDataRoundTripWriter
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def test_roundtrip_writer_adds_data_section(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\n\nstructure=(\n "2025 1 2"\n)\n',
        encoding="utf-8",
    )

    document = _example_document()

    writer = AtlasDataRoundTripWriter()
    result = writer.update_toc(source, document, write=True)

    updated = source.read_text(encoding="utf-8")

    assert "#---data---#" in updated
    assert "TOC;" in updated
    assert result.backup is not None
    assert result.backup.exists()


def test_roundtrip_writer_preserves_existing_heading(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\n'
        "digits=4\n\n"
        "structure=(\n"
        ' "2025 1"\n'
        ")\n\n"
        "#---data---#\n"
        "TOC;oldhash;Example:2025 1;Manually edited heading;u\n",
        encoding="utf-8",
    )

    document = _example_document()

    writer = AtlasDataRoundTripWriter()
    writer.update_toc(source, document, write=True)

    updated = source.read_text(encoding="utf-8")

    assert "Manually edited heading" in updated
    assert "Generated title" not in updated


def test_roundtrip_writer_dry_run_does_not_modify_file(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    original = 'name="Example"\ndigits=4\n\nstructure=(\n "2025 1"\n)\n'
    source.write_text(original, encoding="utf-8")

    writer = AtlasDataRoundTripWriter()
    result = writer.update_toc(source, _example_document(), write=False)

    assert source.read_text(encoding="utf-8") == original
    assert result.backup is None
    assert result.changed is True


def test_roundtrip_writer_creates_numbered_backups(tmp_path: Path) -> None:
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=4\n\nstructure=(\n "2025 1"\n)\n',
        encoding="utf-8",
    )

    writer = AtlasDataRoundTripWriter()

    writer.update_toc(source, _example_document(), write=True)

    # Force another change.
    source.write_text(source.read_text(encoding="utf-8") + "\n# comment\n", encoding="utf-8")

    result = writer.update_toc(source, _example_document(), write=True)

    assert result.backup is not None
    assert result.backup.name == "EXAMPLE.bak.2"


def _example_document() -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="Example",
                    year=2025,
                    clause="1",
                ),
                clause_type=ClauseType.TOC,
                title="Generated title",
            ),
        ),
    )
