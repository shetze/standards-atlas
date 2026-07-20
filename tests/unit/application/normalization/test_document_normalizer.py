from standards_atlas.application.model import (
    ExtractedCode,
    ExtractedDocument,
    ExtractedHeading,
    ExtractedList,
    ExtractedListItem,
    ExtractedText,
    ExtractionMetadata,
    NormalizationOptions,
    NormalizedCode,
    NormalizedList,
    NormalizedText,
)
from standards_atlas.application.normalization import DocumentNormalizer
from standards_atlas.domain.model import (
    BoundingBox,
    CoordinateOrigin,
    SourceEvidence,
)


def evidence(page: int, top: float = 100) -> SourceEvidence:
    return SourceEvidence(
        source_id="sample",
        source_type="pdf",
        page_number=page,
        bounding_box=BoundingBox(left=0, top=top, right=100, bottom=top + 20),
    )


def document(*items):
    return ExtractedDocument(
        source_id="sample",
        items=items,
        metadata=ExtractionMetadata(converter="docling"),
    )


def test_unicode_and_whitespace_are_normalized() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="1",
                sequence_number=0,
                text="Cafe\u0301\u00a0  shall\nwork",
                source_evidence=(evidence(1),),
            )
        )
    )
    item = result.items[0]
    assert isinstance(item, NormalizedText)
    assert item.text == "Café shall work"


def test_code_preserves_indentation_and_line_breaks() -> None:
    code = "if value:\r\n    return  value\r\n"
    result = DocumentNormalizer().normalize(
        document(
            ExtractedCode(
                id="code",
                sequence_number=0,
                code=code,
                source_evidence=(evidence(1),),
                original_label="code",
            )
        )
    )
    item = result.items[0]
    assert isinstance(item, NormalizedCode)
    assert item.code == "if value:\n    return  value"
    assert result.metadata.statistics.code_blocks == 1


def test_repeated_headers_footers_and_page_numbers_are_suppressed() -> None:
    items = []
    for page in range(1, 4):
        items.extend(
            [
                ExtractedText(
                    id=f"h{page}",
                    sequence_number=len(items),
                    text="EN 50716",
                    original_label="page_header",
                    source_evidence=(evidence(page, 20),),
                ),
                ExtractedText(
                    id=f"t{page}",
                    sequence_number=len(items) + 1,
                    text=f"Body text {page}.",
                    source_evidence=(evidence(page, 200),),
                ),
                ExtractedText(
                    id=f"p{page}",
                    sequence_number=len(items) + 2,
                    text=str(page),
                    original_label="page_footer",
                    source_evidence=(evidence(page, 760),),
                ),
            ]
        )
    result = DocumentNormalizer().normalize(document(*items))
    assert len(result.items) == 3
    assert result.metadata.statistics.headers_suppressed == 3
    assert result.metadata.statistics.page_numbers_suppressed == 3


def test_hyphenation_across_items_is_repaired_and_provenance_combined() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="a",
                sequence_number=0,
                text="require-",
                source_evidence=(evidence(1),),
            ),
            ExtractedText(
                id="b",
                sequence_number=1,
                text="ment specification.",
                source_evidence=(evidence(2),),
            ),
        )
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert isinstance(item, NormalizedText)
    assert item.text == "requirement specification."
    assert item.source_item_ids == ("a", "b")
    assert len(item.source_evidence) == 2
    assert result.metadata.statistics.hyphenations_repaired == 1


def test_hyphenated_technical_terms_are_not_changed() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="a",
                sequence_number=0,
                text="SIL-2 requirement",
                source_evidence=(evidence(1),),
            )
        )
    )
    assert result.items[0].text == "SIL-2 requirement"


def test_text_list_markers_are_reconstructed_as_list() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="a",
                sequence_number=0,
                text="a) First",
                source_evidence=(evidence(1),),
            ),
            ExtractedText(
                id="b",
                sequence_number=1,
                text="b) Second",
                source_evidence=(evidence(1),),
            ),
        )
    )
    item = result.items[0]
    assert isinstance(item, NormalizedList)
    assert [entry.text for entry in item.items] == ["First", "Second"]
    assert result.metadata.statistics.lists_normalized == 1


def test_adjacent_extracted_lists_are_consolidated() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="a",
                sequence_number=0,
                ordered=False,
                items=(ExtractedListItem(text="First"),),
                source_evidence=(evidence(1),),
            ),
            ExtractedList(
                id="b",
                sequence_number=1,
                ordered=False,
                items=(ExtractedListItem(text="Second"),),
                source_evidence=(evidence(1),),
            ),
        )
    )
    item = result.items[0]
    assert isinstance(item, NormalizedList)
    assert len(item.items) == 2


def test_normalization_is_deterministic_except_timestamp() -> None:
    source = document(
        ExtractedText(
            id="a",
            sequence_number=0,
            text="Text.",
            source_evidence=(evidence(1),),
        )
    )
    first = DocumentNormalizer().normalize(source)
    second = DocumentNormalizer().normalize(source)
    assert first.items == second.items
    assert first.metadata.source_extraction_hash == second.metadata.source_extraction_hash
    assert first.metadata.options == NormalizationOptions()


def test_multilevel_clause_reference_at_page_start_is_not_suppressed() -> None:
    items = []
    for page, reference in enumerate(("3.1.15", "3.1.24", "3.1.31"), start=1):
        items.append(
            ExtractedText(
                id=f"ref-{page}",
                sequence_number=len(items),
                text=reference,
                original_label="page_header",
                source_evidence=(evidence(page, 20),),
            )
        )
    result = DocumentNormalizer().normalize(document(*items))
    assert [item.text for item in result.items] == ["3.1.15", "3.1.24", "3.1.31"]
    assert result.suppressed_items == ()


def test_clause_reference_signatures_are_not_collapsed_as_repeated_headers() -> None:
    items = tuple(
        ExtractedText(
            id=f"ref-{page}",
            sequence_number=page - 1,
            text=reference,
            source_evidence=(evidence(page, 20),),
        )
        for page, reference in enumerate(("3.1.15", "3.1.24", "3.1.31"), start=1)
    )
    result = DocumentNormalizer().normalize(document(*items))
    assert len(result.items) == 3
    assert result.metadata.statistics.headers_suppressed == 0


def test_clause_reference_is_not_merged_with_following_term() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="ref",
                sequence_number=0,
                text="3.1.15",
                source_evidence=(evidence(1, 20),),
            ),
            ExtractedText(
                id="term",
                sequence_number=1,
                text="availability",
                source_evidence=(evidence(1, 60),),
            ),
        )
    )
    assert len(result.items) == 2
    assert [item.text for item in result.items] == ["3.1.15", "availability"]


def test_clause_like_list_items_become_individual_normalized_text_items() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="#/texts/562",
                sequence_number=0,
                ordered=False,
                original_label="list_item",
                items=(
                    ExtractedListItem(
                        id="#/texts/562",
                        text="4.1 First clause",
                        source_evidence=(evidence(21),),
                    ),
                    ExtractedListItem(
                        id="#/texts/578",
                        text="4.4 Fourth clause",
                        source_evidence=(evidence(21),),
                    ),
                    ExtractedListItem(
                        id="#/texts/579",
                        text="4.5 Fifth clause",
                        source_evidence=(evidence(21),),
                    ),
                ),
                source_evidence=(evidence(21),),
            )
        )
    )

    assert [item.id for item in result.items] == [
        "normalized:#/texts/562",
        "normalized:#/texts/578",
        "normalized:#/texts/579",
    ]
    assert [item.source_item_ids for item in result.items] == [
        ("#/texts/562",),
        ("#/texts/578",),
        ("#/texts/579",),
    ]
    assert [item.text for item in result.items] == [
        "4.1 First clause",
        "4.4 Fourth clause",
        "4.5 Fifth clause",
    ]


def test_ordinary_list_items_remain_grouped_with_individual_source_ids() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="#/texts/10",
                sequence_number=0,
                ordered=False,
                original_label="list_item",
                items=(
                    ExtractedListItem(id="#/texts/10", text="first"),
                    ExtractedListItem(id="#/texts/11", text="second"),
                ),
                source_evidence=(evidence(1),),
            )
        )
    )

    item = result.items[0]
    assert isinstance(item, NormalizedList)
    assert item.source_item_ids == ("#/texts/10", "#/texts/11")
    assert [entry.source_item_ids for entry in item.items] == [
        ("#/texts/10",),
        ("#/texts/11",),
    ]


def test_clause_numbers_in_list_markers_are_restored_in_normalized_text() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="#/texts/562",
                sequence_number=0,
                ordered=True,
                original_label="list_item",
                items=(
                    ExtractedListItem(
                        id="#/texts/562",
                        marker="4.1",
                        text="First clause",
                        source_evidence=(evidence(21),),
                    ),
                    ExtractedListItem(
                        id="#/texts/578",
                        marker="4.4",
                        text="Fourth clause",
                        source_evidence=(evidence(21),),
                    ),
                    ExtractedListItem(
                        id="#/texts/579",
                        marker="4.5",
                        text="Fifth clause",
                        source_evidence=(evidence(21),),
                    ),
                ),
                source_evidence=(evidence(21),),
            )
        )
    )

    assert [item.id for item in result.items] == [
        "normalized:#/texts/562",
        "normalized:#/texts/578",
        "normalized:#/texts/579",
    ]
    assert [item.text for item in result.items] == [
        "4.1 First clause",
        "4.4 Fourth clause",
        "4.5 Fifth clause",
    ]
    assert [item.source_item_ids for item in result.items] == [
        ("#/texts/562",),
        ("#/texts/578",),
        ("#/texts/579",),
    ]


def test_ordinary_list_marker_is_not_promoted_to_clause_reference() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="#/texts/10",
                sequence_number=0,
                ordered=False,
                original_label="list_item",
                items=(
                    ExtractedListItem(
                        id="#/texts/10",
                        marker="—",
                        text="first application",
                    ),
                    ExtractedListItem(
                        id="#/texts/11",
                        marker="—",
                        text="second application",
                    ),
                ),
                source_evidence=(evidence(1),),
            )
        )
    )

    assert len(result.items) == 1
    assert isinstance(result.items[0], NormalizedList)


def test_promoted_clause_items_keep_order_through_normalization() -> None:
    source = document(
        ExtractedText(
            id="#/texts/562",
            sequence_number=0,
            text="4.1 First clause",
            source_evidence=(evidence(21),),
        ),
        ExtractedText(
            id="#/texts/563",
            sequence_number=1,
            text="Text between clauses.",
            source_evidence=(evidence(21),),
        ),
        ExtractedText(
            id="#/texts/578",
            sequence_number=2,
            text="4.4 Fourth clause",
            source_evidence=(evidence(21),),
        ),
        ExtractedText(
            id="#/texts/579",
            sequence_number=3,
            text="4.5 Fifth clause",
            source_evidence=(evidence(21),),
        ),
    )

    result = DocumentNormalizer().normalize(source)

    assert [item.id for item in result.items] == [
        "normalized:#/texts/562",
        "normalized:#/texts/563",
        "normalized:#/texts/578",
        "normalized:#/texts/579",
    ]
    assert [item.sequence_number for item in result.items] == list(range(4))
    assert [item.text for item in result.items] == [
        "4.1 First clause",
        "Text between clauses.",
        "4.4 Fourth clause",
        "4.5 Fifth clause",
    ]


def test_clause_heading_at_bottom_left_page_top_is_not_suppressed() -> None:
    items = tuple(
        ExtractedHeading(
            id=f"heading-{index}",
            sequence_number=index,
            text=f"{reference} Objectives",
            observed_level=1,
            original_label="section_header",
            source_evidence=(
                SourceEvidence(
                    source_id="sample",
                    source_type="pdf",
                    page_number=index + 1,
                    bounding_box=BoundingBox(
                        left=72,
                        top=691,
                        right=200,
                        bottom=701,
                        coordinate_origin=CoordinateOrigin.BOTTOM_LEFT,
                    ),
                ),
            ),
        )
        for index, reference in enumerate(("6.7.1", "7.1.1", "8.1.1"))
    )

    result = DocumentNormalizer().normalize(document(*items))

    assert [item.text for item in result.items] == [
        "6.7.1 Objectives",
        "7.1.1 Objectives",
        "8.1.1 Objectives",
    ]
    assert result.suppressed_items == ()


def test_bottom_left_page_zone_distinguishes_header_and_footer() -> None:
    items = (
        ExtractedText(
            id="header",
            sequence_number=0,
            text="Repeated header",
            source_evidence=(
                SourceEvidence(
                    source_id="sample",
                    source_type="pdf",
                    page_number=1,
                    bounding_box=BoundingBox(
                        left=0,
                        top=710,
                        right=100,
                        bottom=730,
                        coordinate_origin=CoordinateOrigin.BOTTOM_LEFT,
                    ),
                ),
            ),
        ),
        ExtractedText(
            id="footer",
            sequence_number=1,
            text="Repeated footer",
            source_evidence=(
                SourceEvidence(
                    source_id="sample",
                    source_type="pdf",
                    page_number=1,
                    bounding_box=BoundingBox(
                        left=0,
                        top=20,
                        right=100,
                        bottom=40,
                        coordinate_origin=CoordinateOrigin.BOTTOM_LEFT,
                    ),
                ),
            ),
        ),
    )

    from standards_atlas.application.normalization.document_normalizer import _page_zone

    assert _page_zone(items[0]) == "header"
    assert _page_zone(items[1]) == "footer"


def test_positive_page_selection_suppresses_items_outside_range() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(id="p1", sequence_number=0, text="English one.", source_evidence=(evidence(1),)),
            ExtractedText(id="p2", sequence_number=1, text="English two.", source_evidence=(evidence(2),)),
            ExtractedText(id="p3", sequence_number=2, text="Français.", source_evidence=(evidence(3),)),
        ),
        NormalizationOptions(page_ranges=((1, 2),)),
    )
    assert [item.text for item in result.items] == ["English one.", "English two."]
    assert [item.reason for item in result.suppressed_items] == ["content_selection"]
    assert result.metadata.statistics.source_pages == 3
    assert result.metadata.statistics.selected_pages == 2
    assert result.metadata.statistics.excluded_pages == 1


def test_open_ended_page_selection_keeps_pages_from_start() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(id="p1", sequence_number=0, text="Before.", source_evidence=(evidence(1),)),
            ExtractedText(id="p2", sequence_number=1, text="Selected.", source_evidence=(evidence(2),)),
            ExtractedText(id="p3", sequence_number=2, text="Also selected.", source_evidence=(evidence(3),)),
        ),
        NormalizationOptions(page_ranges=((2, None),)),
    )
    assert [item.text for item in result.items] == ["Selected.", "Also selected."]


def test_positive_page_list_selects_individual_pages_and_ranges() -> None:
    result = DocumentNormalizer().normalize(
        document(*(
            ExtractedText(
                id=f"p{page}",
                sequence_number=page - 1,
                text=f"Page {page}",
                source_evidence=(evidence(page),),
            )
            for page in range(1, 7)
        )),
        NormalizationOptions(page_list=(1, 3, 5, 6)),
    )
    assert [item.text for item in result.items] == ["Page 1", "Page 3", "Page 5", "Page 6"]
    assert result.metadata.statistics.selected_pages == 4
    assert result.metadata.statistics.excluded_pages == 2


def test_exclude_page_ranges_are_subtracted_from_positive_selection() -> None:
    result = DocumentNormalizer().normalize(
        document(*(
            ExtractedText(
                id=f"p{page}",
                sequence_number=page - 1,
                text=f"Page {page}",
                source_evidence=(evidence(page),),
            )
            for page in range(1, 6)
        )),
        NormalizationOptions(
            page_ranges=((1, 5),),
            exclude_page_ranges=((2, 4),),
            page_list=(3,),
        ),
    )
    assert [item.text for item in result.items] == ["Page 1", "Page 5"]
