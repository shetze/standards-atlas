from standards_atlas.application.model.normalized_document import NormalizationOptions
from standards_atlas.application.normalization.text import (
    normalize_code,
    normalize_optional_text,
    normalize_text,
)


def test_normalize_text_preserves_existing_semantics() -> None:
    options = NormalizationOptions()

    assert normalize_text("  alpha\u00a0 beta\n gamma  ", options) == "alpha beta gamma"
    assert normalize_optional_text(None, options) is None


def test_normalize_code_preserves_lines_and_tabs() -> None:
    options = NormalizationOptions()

    assert normalize_code("\r\nalpha\r\n\tbeta\r\n", options) == "alpha\n\tbeta"
