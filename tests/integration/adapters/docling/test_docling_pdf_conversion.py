from pathlib import Path

import pytest

from standards_atlas.adapters.docling import DoclingJsonReader, DoclingPdfConverter

pytestmark = pytest.mark.docling


@pytest.mark.skipif(
    pytest.importorskip("docling", reason="Docling optional dependency is not installed") is None,
    reason="Docling optional dependency is not installed",
)
def test_real_pdf_conversion_roundtrip(tmp_path: Path) -> None:
    source = Path("tests/fixtures/pdf/minimal-standard.pdf")
    target = tmp_path / ".atlas" / "docling" / "MIN-STD" / "document.json"

    generated = DoclingPdfConverter().convert(source, target)
    extracted = DoclingJsonReader().read(generated)

    assert generated.is_file()
    assert generated.stat().st_size > 0
    assert extracted.items
    assert any(item.source_evidence for item in extracted.items)
    assert [item.sequence_number for item in extracted.items] == list(range(len(extracted.items)))
