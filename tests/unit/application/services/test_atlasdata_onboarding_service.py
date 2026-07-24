from __future__ import annotations

import json
from pathlib import Path

import pytest

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.application.services import (
    AtlasDataOnboardingError,
    AtlasDataOnboardingService,
    DoclingPartSource,
)


def _write_docling(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "texts": [
                    {
                        "self_ref": "#/texts/0",
                        "label": "section_header",
                        "text": "1 Scope",
                    },
                    {
                        "self_ref": "#/texts/1",
                        "label": "section_header",
                        "text": "3 Terms and definitions",
                    },
                    {
                        "self_ref": "#/texts/2",
                        "label": "section_header",
                        "text": "3.1",
                    },
                    {
                        "self_ref": "#/texts/3",
                        "label": "section_header",
                        "text": "access control",
                    },
                    {
                        "self_ref": "#/texts/4",
                        "label": "section_header",
                        "text": "3.2 attack",
                    },
                    {
                        "self_ref": "#/texts/5",
                        "label": "section_header",
                        "text": "4 Security objectives",
                    },
                    {
                        "self_ref": "#/texts/6",
                        "label": "section_header",
                        "text": "5 General requirements",
                    },
                    {
                        "self_ref": "#/texts/7",
                        "label": "section_header",
                        "text": "ISO/IEC 27000:2018(E)",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_discovers_inline_and_split_clause_headings(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    _write_docling(source)
    document = json.loads(source.read_text(encoding="utf-8"))

    clauses = AtlasDataOnboardingService().discover_clauses(document)

    assert [clause.reference for clause in clauses] == ["1", "3", "3.1", "3.2", "4", "5"]
    assert clauses[2].title == "access control"
    assert clauses[2].source_item_ids == ("#/texts/2", "#/texts/3")
    assert clauses[2].type_marker == "t"
    assert clauses[3].title == "attack"
    assert [clause.type_marker for clause in clauses] == ["s", "t", "t", "t", "o", "r"]


def test_generates_importable_public_atlasdata_file(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    output = tmp_path / "IEC27000"
    _write_docling(source)

    result = AtlasDataOnboardingService().generate(
        source,
        output,
        standard_name="ISO/IEC 27000",
        year=2018,
    )
    imported = AtlasDataImporter().import_document(output)

    assert result.output == output
    assert len(imported.clauses) == 6
    assert imported.clauses[2].reference.clause == "3.1"
    assert imported.clauses[2].title == "access control"
    text = output.read_text(encoding="utf-8")
    assert "s1" in text
    assert "t3 t3.{1..2}" in text
    assert "o4" in text
    assert "r5" in text
    assert imported.clauses[0].semantic_roles == ("scope",)
    assert imported.clauses[2].semantic_roles == ("terms_and_definitions",)
    assert imported.clauses[4].semantic_roles == ("objectives",)
    assert imported.clauses[5].semantic_roles == ("requirements",)
    assert "Clause text is intentionally not included" in text


def test_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    output = tmp_path / "IEC27000"
    _write_docling(source)
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(AtlasDataOnboardingError, match="already exists"):
        AtlasDataOnboardingService().generate(
            source,
            output,
            standard_name="ISO/IEC 27000",
            year=2018,
        )


def test_compresses_only_contiguous_sibling_sequences(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    output = tmp_path / "EXAMPLE"
    source.write_text(
        json.dumps(
            {
                "texts": [
                    {"self_ref": "#/texts/0", "label": "section_header", "text": "1 Scope"},
                    {"self_ref": "#/texts/1", "label": "section_header", "text": "2 References"},
                    {
                        "self_ref": "#/texts/2",
                        "label": "section_header",
                        "text": "3 Terms and definitions",
                    },
                    {"self_ref": "#/texts/3", "label": "section_header", "text": "3.1 first"},
                    {"self_ref": "#/texts/4", "label": "section_header", "text": "3.2 second"},
                    {"self_ref": "#/texts/5", "label": "section_header", "text": "4 Overview"},
                    {"self_ref": "#/texts/6", "label": "section_header", "text": "4.1 one"},
                    {"self_ref": "#/texts/7", "label": "section_header", "text": "4.2 two"},
                    {"self_ref": "#/texts/8", "label": "section_header", "text": "4.2.1 nested"},
                    {"self_ref": "#/texts/9", "label": "section_header", "text": "4.3 three"},
                    {"self_ref": "#/texts/10", "label": "section_header", "text": "4.4 four"},
                ]
            }
        ),
        encoding="utf-8",
    )

    AtlasDataOnboardingService().generate(source, output, standard_name="Example", year=2026)

    text = output.read_text(encoding="utf-8")
    assert '"2026 s1 2 t3 t3.{1..2} 4 4.{1..2} 4.2.1 4.{3..4}"' in text

    imported = AtlasDataImporter().import_document(output)
    assert [clause.reference.clause for clause in imported.clauses] == [
        "1",
        "2",
        "3",
        "3.1",
        "3.2",
        "4",
        "4.1",
        "4.2",
        "4.2.1",
        "4.3",
        "4.4",
    ]


def test_generates_multi_part_atlasdata_with_explicit_part_context(tmp_path: Path) -> None:
    part_1 = tmp_path / "part1.json"
    part_2 = tmp_path / "part2.json"
    output = tmp_path / "IEC11889"
    part_1.write_text(
        json.dumps(
            {
                "name": "IEC-11889-1_2015",
                "texts": [
                    {"self_ref": "#/texts/0", "label": "section_header", "text": "1 Scope"},
                    {
                        "self_ref": "#/texts/1",
                        "label": "section_header",
                        "text": "Annex A (normative)",
                    },
                    {"self_ref": "#/texts/2", "label": "section_header", "text": "A.1 Algorithms"},
                ],
            }
        ),
        encoding="utf-8",
    )
    part_2.write_text(
        json.dumps(
            {
                "name": "IEC-11889-2_2015",
                "texts": [
                    {"self_ref": "#/texts/0", "label": "section_header", "text": "1 Scope"},
                    {
                        "self_ref": "#/texts/1",
                        "label": "section_header",
                        "text": "2 Normative references",
                    },
                    {
                        "self_ref": "#/texts/2",
                        "label": "section_header",
                        "text": "Annex A (informative) Implementation definitions",
                    },
                    {"self_ref": "#/texts/3", "label": "section_header", "text": "A.1 Limits"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = AtlasDataOnboardingService().generate_parts(
        (
            DoclingPartSource(2, part_2),
            DoclingPartSource(1, part_1),
        ),
        output,
        standard_name="IEC 11889",
        year=2015,
    )

    assert [part.part for part in result.parts] == ["1", "2"]
    text = output.read_text(encoding="utf-8")
    assert '"2015 1-0 1-s1 1-2:A 1-2:A.1"' in text
    assert '"2015 2-0 2-s1 2-2 2-3:A 2-3:A.1"' in text
    assert "IEC 11889-1:2015 0;Part 1;u" in text
    assert "IEC 11889-1:2015 A;Annex A (normative);u" in text
    assert "IEC 11889-2:2015 0;Part 2;u" in text
    assert "IEC 11889-2:2015 A;Annex A (informative) Implementation definitions;u" in text

    imported = AtlasDataImporter().import_document(output)
    assert len(imported.clauses) == 9
    assert text.count("IEC 11889-1:2015 A;") == 1
    assert text.count("IEC 11889-2:2015 A;") == 1


def test_rejects_duplicate_part_assignments(tmp_path: Path) -> None:
    source = tmp_path / "part.json"
    _write_docling(source)
    with pytest.raises(AtlasDataOnboardingError, match="Duplicate part assignments"):
        AtlasDataOnboardingService().generate_parts(
            (DoclingPartSource(1, source), DoclingPartSource(1, source)),
            tmp_path / "out",
            standard_name="Example",
            year=2026,
        )


def test_annex_heading_can_follow_annex_subclause_in_docling_order() -> None:
    document = {
        "texts": [
            {"self_ref": "#/texts/0", "label": "section_header", "text": "1 Scope"},
            {"self_ref": "#/texts/1", "label": "section_header", "text": "A.1 Introduction"},
            {"self_ref": "#/texts/2", "label": "section_header", "text": "Annex A (informative)"},
            {"self_ref": "#/texts/3", "label": "section_header", "text": "A.2 Details"},
        ]
    }

    clauses = AtlasDataOnboardingService().discover_clauses(document)

    assert [clause.reference for clause in clauses] == ["1", "A", "A.1", "A.2"]
    assert clauses[1].title == "Annex A (informative)"
    assert clauses[1].annex_status == "informative"


def test_generates_canonical_typed_annex_tokens() -> None:
    from standards_atlas.application.services.atlasdata_onboarding_service import (
        DiscoveredClause,
        _render_structure_tokens,
    )

    tokens = _render_structure_tokens(
        (
            DiscoveredClause(
                reference="1",
                title="Scope",
                type_marker="s",
                source_item_ids=("#/texts/0",),
            ),
            DiscoveredClause(
                reference="C",
                title="Annex C",
                type_marker="u",
                source_item_ids=("#/texts/1",),
            ),
            DiscoveredClause(
                reference="C.1",
                title="Requirement",
                type_marker="r",
                source_item_ids=("#/texts/2",),
            ),
        ),
        None,
    )

    assert "r2:C.1" in tokens
    assert "2:rC.1" not in tokens


def test_generated_atlasdata_is_proposed(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    output = tmp_path / "IEC27000"
    _write_docling(source)

    AtlasDataOnboardingService().generate(source, output, standard_name="ISO/IEC 27000", year=2018)

    assert 'lifecycle_status="proposed"' in output.read_text(encoding="utf-8")


def test_refuses_to_overwrite_reviewed_atlasdata(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    output = tmp_path / "IEC27000"
    _write_docling(source)
    output.write_text(
        'name="ISO/IEC 27000"\ndigits=8\nlifecycle_status="reviewed"\nstructure=(\n "2018 1"\n)\n',
        encoding="utf-8",
    )

    with pytest.raises(AtlasDataOnboardingError, match="cannot be overwritten"):
        AtlasDataOnboardingService().generate(
            source,
            output,
            standard_name="ISO/IEC 27000",
            year=2018,
            overwrite=True,
        )
