from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.adapters.pdf import FormulaVisualExtractor
from standards_atlas.application.model import (
    ExtractedDocument,
    ExtractedFormula,
    ExtractionMetadata,
    LayoutEvidence,
)
from standards_atlas.domain.model import BoundingBox, CoordinateOrigin, SourceEvidence

pymupdf = pytest.importorskip("pymupdf")


def _document(*, origin: CoordinateOrigin) -> ExtractedDocument:
    return ExtractedDocument(
        source_id="sample",
        items=(
            ExtractedFormula(
                id="formula-1",
                sequence_number=0,
                expression="",
                extraction_status="visual_only",
                source_evidence=(
                    SourceEvidence(
                        source_id="sample",
                        source_type="pdf",
                        page_number=1,
                        bounding_box=BoundingBox(
                            left=45,
                            top=45,
                            right=155,
                            bottom=75,
                            coordinate_origin=origin,
                        ),
                    ),
                ),
                layout_evidence=(LayoutEvidence(page_width=200, page_height=200),),
            ),
        ),
        metadata=ExtractionMetadata(converter="docling"),
    )


def _write_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((50, 65), "E = mc^2", fontsize=16)
    document.save(path)
    document.close()


def test_visual_only_formula_gets_png_asset(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _write_pdf(source)

    result = FormulaVisualExtractor(dpi=144, padding_points=2).enrich(
        _document(origin=CoordinateOrigin.TOP_LEFT), source
    )

    formula = result.items[0]
    assert isinstance(formula, ExtractedFormula)
    assert formula.visual_asset is not None
    assert formula.visual_asset.media_type == "image/png"
    assert formula.visual_asset.data_uri is not None
    assert formula.visual_asset.data_uri.startswith("data:image/png;base64,")
    assert len(formula.visual_asset.content_hash) == 64


def test_bottom_left_coordinates_are_converted_to_pdf_clip_space(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _write_pdf(source)
    document = _document(origin=CoordinateOrigin.BOTTOM_LEFT)
    formula = document.items[0]
    assert isinstance(formula, ExtractedFormula)
    # In bottom-left coordinates the same visual band at y=45..75 from the top is 125..155.
    converted = formula.model_copy(
        update={
            "source_evidence": (
                formula.source_evidence[0].model_copy(
                    update={
                        "bounding_box": BoundingBox(
                            left=45,
                            top=125,
                            right=155,
                            bottom=155,
                            coordinate_origin=CoordinateOrigin.BOTTOM_LEFT,
                        )
                    }
                ),
            )
        }
    )
    document = document.model_copy(update={"items": (converted,)})

    result = FormulaVisualExtractor(dpi=144, padding_points=2).enrich(document, source)

    rendered = result.items[0]
    assert isinstance(rendered, ExtractedFormula)
    assert rendered.visual_asset is not None
    assert rendered.visual_asset.width > 0
    assert rendered.visual_asset.height > 0


def test_machine_extracted_formula_is_not_rasterized(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _write_pdf(source)
    document = _document(origin=CoordinateOrigin.TOP_LEFT)
    formula = document.items[0]
    assert isinstance(formula, ExtractedFormula)
    document = document.model_copy(
        update={
            "items": (
                formula.model_copy(
                    update={"expression": "E = mc^2", "extraction_status": "machine_extracted"}
                ),
            )
        }
    )

    result = FormulaVisualExtractor().enrich(document, source)

    rendered = result.items[0]
    assert isinstance(rendered, ExtractedFormula)
    assert rendered.visual_asset is None
