import json
from pathlib import Path

from standards_atlas.application.services.atlasdata_onboarding_service import (
    AtlasDataOnboardingService,
    DoclingPartSource,
    _detect_part_from_metadata,
)


def test_detects_supplement_identifier_from_metadata() -> None:
    assert _detect_part_from_metadata("iec61508-3-1{ed1.0}en.pdf", 2010) == "3-1"


def test_part_source_accepts_supplement_identifier() -> None:
    source = DoclingPartSource.parse("3-1=.atlas/data/docling/IEC61508-3-1/document.json")
    assert source.part == "3-1"


def test_single_part_onboarding_does_not_validate_synthetic_part_against_year(
    tmp_path: Path,
) -> None:
    source = tmp_path / "document.json"
    source.write_text(
        json.dumps(
            {
                "name": "ISO+SAE+21434-2021.pdf",
                "origin": {"filename": "ISO+SAE+21434-2021.pdf"},
                "texts": [
                    {
                        "self_ref": "#/texts/0",
                        "label": "section_header",
                        "text": "1 Scope",
                        "prov": [{"page_no": 1}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = AtlasDataOnboardingService().generate(
        source,
        tmp_path / "ISO21434",
        standard_name="ISO/SAE 21434",
        year=2021,
    )
    assert result.standard_name == "ISO/SAE 21434"


def test_multi_part_metadata_keeps_compound_part_identity(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    source.write_text(
        json.dumps(
            {
                "name": "IEC61508-3-1",
                "origin": {"filename": "iec61508-3-1{ed1.0}en.pdf"},
                "texts": [
                    {
                        "self_ref": "#/texts/0",
                        "label": "section_header",
                        "text": "1 Scope",
                        "prov": [{"page_no": 1}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = AtlasDataOnboardingService().generate_parts(
        (DoclingPartSource(part="3-1", path=source),),
        tmp_path / "IEC61508",
        standard_name="IEC 61508",
        year=2010,
    )
    assert result.parts[0].part == "3-1"


def test_detect_part_ignores_trailing_publication_year() -> None:
    from standards_atlas.application.services.atlasdata_onboarding_service import (
        _detect_part_from_metadata,
    )

    assert _detect_part_from_metadata("ISO+26262-8-2018.pdf", 2018) == "8"
    assert _detect_part_from_metadata("ISO+SAE+21434-2021.pdf", 2021) is None
    assert _detect_part_from_metadata("IEC61508-3-1.pdf", 2010) == "3-1"
