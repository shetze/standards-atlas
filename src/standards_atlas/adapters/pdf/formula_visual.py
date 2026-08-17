"""Deterministically render known formula regions from source PDFs."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from standards_atlas.application.model import ExtractedDocument, ExtractedFormula, VisualAsset
from standards_atlas.domain.model import CoordinateOrigin


class FormulaVisualExtractor:
    """Attach PNG assets to formulas already located by the primary extractor.

    This adapter deliberately does not discover formulas. It only renders formula
    regions for ``visual_only`` items with usable page and bounding-box evidence.
    """

    def __init__(self, *, dpi: int = 300, padding_points: float = 4.0) -> None:
        if dpi <= 0:
            raise ValueError("formula rendering dpi must be greater than zero")
        if padding_points < 0:
            raise ValueError("formula rendering padding must not be negative")
        self._dpi = dpi
        self._padding_points = padding_points

    def enrich(self, document: ExtractedDocument, source_pdf: Path) -> ExtractedDocument:
        """Return ``document`` with deterministic PNG assets for visual-only formulas."""
        if source_pdf.suffix.lower() != ".pdf":
            raise ValueError(f"Formula visual extraction requires a PDF source: {source_pdf}")
        if not source_pdf.is_file():
            raise FileNotFoundError(source_pdf)

        pymupdf = _load_pymupdf()
        changed = False
        items = []
        with pymupdf.open(source_pdf) as pdf:
            for item in document.items:
                if not _requires_visual_asset(item):
                    items.append(item)
                    continue
                asset = self._render_formula(item, pdf, pymupdf)
                if asset is None:
                    items.append(item)
                    continue
                items.append(item.model_copy(update={"visual_asset": asset}))
                changed = True
        return document.model_copy(update={"items": tuple(items)}) if changed else document

    def _render_formula(self, item: ExtractedFormula, pdf: Any, pymupdf: Any) -> VisualAsset | None:
        evidence = next(
            (
                value
                for value in item.source_evidence
                if value.page_number is not None and value.bounding_box is not None
            ),
            None,
        )
        if evidence is None:
            return None
        page_index = evidence.page_number - 1
        if page_index < 0 or page_index >= len(pdf):
            return None

        page = pdf[page_index]
        box = evidence.bounding_box
        source_width, source_height = _source_page_dimensions(item)
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        scale_x = page_width / source_width if source_width else 1.0
        scale_y = page_height / source_height if source_height else 1.0

        left = box.left * scale_x
        right = box.right * scale_x
        if box.coordinate_origin is CoordinateOrigin.BOTTOM_LEFT:
            top = page_height - (box.bottom * scale_y)
            bottom = page_height - (box.top * scale_y)
        else:
            top = box.top * scale_y
            bottom = box.bottom * scale_y

        padding = self._padding_points
        clip = pymupdf.Rect(
            max(0.0, left - padding),
            max(0.0, top - padding),
            min(page_width, right + padding),
            min(page_height, bottom + padding),
        )
        if clip.is_empty or clip.is_infinite:
            return None

        matrix = pymupdf.Matrix(self._dpi / 72.0, self._dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        payload = pixmap.tobytes("png")
        digest = hashlib.sha256(payload).hexdigest()
        encoded = base64.b64encode(payload).decode("ascii")
        return VisualAsset(
            media_type="image/png",
            content_hash=digest,
            data_uri=f"data:image/png;base64,{encoded}",
            width=float(pixmap.width),
            height=float(pixmap.height),
        )


def _requires_visual_asset(item: object) -> bool:
    return (
        isinstance(item, ExtractedFormula)
        and item.extraction_status == "visual_only"
        and item.visual_asset is None
    )


def _source_page_dimensions(item: ExtractedFormula) -> tuple[float | None, float | None]:
    for evidence in item.layout_evidence:
        if evidence.page_width is not None and evidence.page_height is not None:
            return evidence.page_width, evidence.page_height
    return None, None


def _load_pymupdf() -> Any:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency declaration guards this path
        raise RuntimeError(
            "Formula visual extraction requires PyMuPDF, which is a required runtime dependency. "
            "Run 'uv sync' to restore the project environment."
        ) from exc
    return pymupdf
