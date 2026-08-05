from __future__ import annotations

from standards_atlas.shared.formatting import (
    format_decimal,
    format_gigabytes,
    format_percentage,
    format_seconds,
)


def test_optional_metric_formatters_use_consistent_defaults() -> None:
    assert format_decimal(0.123456) == "0.1235"
    assert format_decimal(None) == "n/a"
    assert format_percentage(0.125) == "12.5%"
    assert format_seconds(1.234) == "1.23s"
    assert format_gigabytes(3.456) == "3.46GB"


def test_metric_formatters_allow_report_specific_precision_and_missing_marker() -> None:
    assert format_decimal(1.2345, digits=2) == "1.23"
    assert format_percentage(None, missing="-") == "-"
    assert format_seconds(1.2345, digits=3) == "1.234s"
