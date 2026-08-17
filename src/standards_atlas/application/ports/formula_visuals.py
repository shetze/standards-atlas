"""Ports for deterministic visual preservation of already identified formulas."""

from pathlib import Path
from typing import Protocol

from standards_atlas.application.model import ExtractedDocument


class FormulaVisualEnricher(Protocol):
    """Attach source-derived visual assets without performing formula discovery."""

    def enrich(self, document: ExtractedDocument, source_pdf: Path) -> ExtractedDocument: ...
