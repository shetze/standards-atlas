import pytest

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
from standards_atlas.application.normalization import (
    DocumentNormalizer,
    NormalizationDataLossError,
)
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


def test_normalizer_version_is_decoupled_from_package_release() -> None:
    result = DocumentNormalizer().normalize(document())
    assert result.metadata.normalizer_version == "0.7.0"


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


def test_normalization_is_fully_deterministic() -> None:
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
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


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

    assert all(item.id.startswith("normalized:") for item in result.items)
    assert len({item.id for item in result.items}) == 3
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

    assert all(item.id.startswith("normalized:") for item in result.items)
    assert len({item.id for item in result.items}) == 3
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

    assert all(item.id.startswith("normalized:") for item in result.items)
    assert len({item.id for item in result.items}) == 4
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
            ExtractedText(
                id="p1", sequence_number=0, text="English one.", source_evidence=(evidence(1),)
            ),
            ExtractedText(
                id="p2", sequence_number=1, text="English two.", source_evidence=(evidence(2),)
            ),
            ExtractedText(
                id="p3", sequence_number=2, text="Français.", source_evidence=(evidence(3),)
            ),
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
            ExtractedText(
                id="p1", sequence_number=0, text="Before.", source_evidence=(evidence(1),)
            ),
            ExtractedText(
                id="p2", sequence_number=1, text="Selected.", source_evidence=(evidence(2),)
            ),
            ExtractedText(
                id="p3", sequence_number=2, text="Also selected.", source_evidence=(evidence(3),)
            ),
        ),
        NormalizationOptions(page_ranges=((2, None),)),
    )
    assert [item.text for item in result.items] == ["Selected.", "Also selected."]


def test_positive_page_list_selects_individual_pages_and_ranges() -> None:
    result = DocumentNormalizer().normalize(
        document(
            *(
                ExtractedText(
                    id=f"p{page}",
                    sequence_number=page - 1,
                    text=f"Page {page}",
                    source_evidence=(evidence(page),),
                )
                for page in range(1, 7)
            )
        ),
        NormalizationOptions(page_list=(1, 3, 5, 6)),
    )
    assert [item.text for item in result.items] == ["Page 1", "Page 3", "Page 5", "Page 6"]
    assert result.metadata.statistics.selected_pages == 4
    assert result.metadata.statistics.excluded_pages == 2


def test_exclude_page_ranges_are_subtracted_from_positive_selection() -> None:
    result = DocumentNormalizer().normalize(
        document(
            *(
                ExtractedText(
                    id=f"p{page}",
                    sequence_number=page - 1,
                    text=f"Page {page}",
                    source_evidence=(evidence(page),),
                )
                for page in range(1, 6)
            )
        ),
        NormalizationOptions(
            page_ranges=((1, 5),),
            exclude_page_ranges=((2, 4),),
            page_list=(3,),
        ),
    )
    assert [item.text for item in result.items] == ["Page 1", "Page 5"]


def test_source_item_accounting_reports_active_and_suppressed_units() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="active",
                sequence_number=0,
                text="Normative content.",
                source_evidence=(evidence(1),),
            ),
            ExtractedText(
                id="page-number",
                sequence_number=1,
                text="1",
                source_evidence=(evidence(1, 760),),
            ),
        )
    )

    statistics = result.metadata.statistics
    assert statistics.active_source_items == 1
    assert statistics.suppressed_source_items == 1
    assert statistics.unaccounted_source_items == 0
    assert statistics.duplicate_source_items == 0


def test_unique_explicit_page_header_remains_active() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="header",
                sequence_number=0,
                text="Unique normative heading",
                original_label="page_header",
                source_evidence=(evidence(1, 20),),
            )
        )
    )

    assert [item.text for item in result.items] == ["Unique normative heading"]
    assert result.suppressed_items == ()


def test_unlabelled_repeated_page_elements_require_explicit_option() -> None:
    items = tuple(
        ExtractedText(
            id=f"header-{page}",
            sequence_number=page - 1,
            text="Repeated page furniture",
            source_evidence=(evidence(page, 20),),
        )
        for page in range(1, 4)
    )

    retained = DocumentNormalizer().normalize(document(*items))
    suppressed = DocumentNormalizer().normalize(
        document(*items),
        NormalizationOptions(suppress_repeated_page_elements=True),
    )

    assert len(retained.items) == 3
    assert retained.suppressed_items == ()
    assert suppressed.items == ()
    assert [item.source_item_id for item in suppressed.suppressed_items] == [
        "header-1",
        "header-2",
        "header-3",
    ]


def test_text_list_reconstruction_preserves_extracted_source_ids() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(id="a", sequence_number=0, text="a) First"),
            ExtractedText(id="b", sequence_number=1, text="b) Second"),
        )
    )

    assert result.items[0].source_item_ids == ("a", "b")
    assert result.metadata.statistics.active_source_items == 2


def test_missing_source_item_raises_data_loss_error() -> None:
    class DroppingNormalizer(DocumentNormalizer):
        def _map_items(self, item, options):
            if item.id == "dropped":
                return []
            return super()._map_items(item, options)

    with pytest.raises(NormalizationDataLossError) as error:
        DroppingNormalizer().normalize(
            document(ExtractedText(id="dropped", sequence_number=0, text="Lost"))
        )

    assert error.value.missing_item_ids == ("dropped",)
    assert error.value.duplicate_item_ids == ()


def test_duplicate_source_item_raises_data_loss_error() -> None:
    class DuplicatingNormalizer(DocumentNormalizer):
        def _map_items(self, item, options):
            mapped = super()._map_items(item, options)
            return mapped + mapped

    with pytest.raises(NormalizationDataLossError) as error:
        DuplicatingNormalizer().normalize(
            document(ExtractedText(id="duplicate", sequence_number=0, text="Repeated."))
        )

    assert error.value.missing_item_ids == ()
    assert error.value.duplicate_item_ids == ("duplicate",)


def test_data_loss_can_be_reported_without_failing() -> None:
    class DroppingNormalizer(DocumentNormalizer):
        def _map_items(self, item, options):
            return []

    result = DroppingNormalizer().normalize(
        document(ExtractedText(id="dropped", sequence_number=0, text="Lost")),
        NormalizationOptions(fail_on_data_loss=False),
    )

    assert result.metadata.statistics.unaccounted_source_items == 1
    assert result.metadata.statistics.duplicate_source_items == 0


def test_item_identity_is_stable_when_sequence_number_changes() -> None:
    first_source = document(
        ExtractedText(
            id="source-a",
            sequence_number=0,
            text="Text.",
            source_evidence=(evidence(1),),
        )
    )
    second_source = document(
        ExtractedText(
            id="source-a",
            sequence_number=99,
            text="Text.",
            source_evidence=(evidence(1),),
        )
    )

    first = DocumentNormalizer().normalize(first_source)
    second = DocumentNormalizer().normalize(second_source)

    assert first.items[0].id == second.items[0].id


def test_item_identity_changes_when_source_lineage_changes() -> None:
    first = DocumentNormalizer().normalize(
        document(ExtractedText(id="source-a", sequence_number=0, text="Text."))
    )
    second = DocumentNormalizer().normalize(
        document(ExtractedText(id="source-b", sequence_number=0, text="Text."))
    )

    assert first.items[0].id != second.items[0].id


def test_normalization_preserves_layout_evidence_for_text_and_lists() -> None:
    from standards_atlas.application.model import LayoutEvidence

    text_layout = LayoutEvidence(
        source_reference="#/texts/0",
        content_layer="body",
        parent_reference="#/body",
        page_width=595.0,
        page_height=842.0,
        original_text="Original  text",
    )
    list_layout = LayoutEvidence(
        source_reference="#/texts/1",
        content_layer="body",
        parent_reference="#/groups/0",
        group_path=("#/groups/0",),
        page_width=595.0,
        page_height=842.0,
        original_marker="-",
        original_text="- child",
    )
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="text",
                sequence_number=0,
                text="Original  text",
                source_evidence=(evidence(1),),
                layout_evidence=(text_layout,),
            ),
            ExtractedList(
                id="list",
                sequence_number=1,
                items=(
                    ExtractedListItem(
                        id="list-item",
                        sequence_number=1,
                        text="child",
                        marker="-",
                        source_evidence=(evidence(1),),
                        layout_evidence=(list_layout,),
                    ),
                ),
                source_evidence=(evidence(1),),
                layout_evidence=(list_layout,),
                original_label="list_item",
            ),
        )
    )

    assert result.items[0].layout_evidence == (text_layout,)
    normalized_list = result.items[1]
    assert isinstance(normalized_list, NormalizedList)
    assert normalized_list.layout_evidence == (list_layout,)
    assert normalized_list.items[0].layout_evidence == (list_layout,)


def test_merged_text_preserves_layout_evidence_from_all_sources() -> None:
    from standards_atlas.application.model import LayoutEvidence

    first_layout = LayoutEvidence(source_reference="#/texts/0", original_text="first")
    second_layout = LayoutEvidence(source_reference="#/texts/1", original_text="continuation")
    result = DocumentNormalizer().normalize(
        document(
            ExtractedText(
                id="first",
                sequence_number=0,
                text="first",
                source_evidence=(evidence(1),),
                layout_evidence=(first_layout,),
            ),
            ExtractedText(
                id="second",
                sequence_number=1,
                text="continuation",
                source_evidence=(evidence(1),),
                layout_evidence=(second_layout,),
            ),
        )
    )

    assert result.items[0].layout_evidence == (first_layout, second_layout)


def _layout(page_height: float = 842.0):
    from standards_atlas.application.model import LayoutEvidence

    return (LayoutEvidence(page_width=595.0, page_height=page_height),)


def _bottom_left_evidence(page: int, bottom: float, top: float) -> SourceEvidence:
    return SourceEvidence(
        source_id="sample",
        source_type="pdf",
        page_number=page,
        bounding_box=BoundingBox(
            left=66.6,
            top=min(bottom, top),
            right=164.4,
            bottom=max(bottom, top),
            coordinate_origin=CoordinateOrigin.BOTTOM_LEFT,
        ),
    )


def test_repeated_margin_classifier_corrects_docling_section_header_labels() -> None:
    items = tuple(
        ExtractedHeading(
            id=f"header-{page}",
            sequence_number=page - 1,
            text="EN 50126-1:2017 (E)",
            original_label="section_header",
            source_evidence=(_bottom_left_evidence(page, 793.5, 803.3),),
            layout_evidence=_layout(),
        )
        for page in range(4, 9)
    )

    result = DocumentNormalizer().normalize(document(*items))

    assert result.items == ()
    assert result.metadata.statistics.headers_suppressed == 5
    assert {decision.role for decision in result.page_furniture_decisions} == {"page_header"}
    assert {decision.rule_id for decision in result.page_furniture_decisions} == {
        "repeated-margin-text"
    }
    assert {decision.original_label for decision in result.page_furniture_decisions} == {
        "section_header"
    }
    assert all(decision.distinct_pages == 5 for decision in result.page_furniture_decisions)


def test_repeated_body_text_is_not_classified_as_page_furniture() -> None:
    items = tuple(
        ExtractedText(
            id=f"body-{page}",
            sequence_number=page - 1,
            text="The system shall be validated.",
            original_label="text",
            source_evidence=(_bottom_left_evidence(page, 390.0, 410.0),),
            layout_evidence=_layout(),
        )
        for page in range(1, 5)
    )

    result = DocumentNormalizer().normalize(document(*items))

    assert len(result.items) == 4
    assert result.page_furniture_decisions == ()


def test_repeated_clause_anchor_in_margin_is_protected() -> None:
    items = tuple(
        ExtractedHeading(
            id=f"anchor-{page}",
            sequence_number=page - 1,
            text="7.4.2 Requirement",
            original_label="section_header",
            source_evidence=(_bottom_left_evidence(page, 793.5, 803.3),),
            layout_evidence=_layout(),
        )
        for page in range(1, 4)
    )

    result = DocumentNormalizer().normalize(document(*items))

    assert len(result.items) == 3
    assert result.page_furniture_decisions == ()


def test_repeated_footer_is_detected_from_bottom_left_coordinates() -> None:
    items = tuple(
        ExtractedText(
            id=f"footer-{page}",
            sequence_number=page - 1,
            text="© CENELEC 2017",
            original_label="text",
            source_evidence=(_bottom_left_evidence(page, 25.0, 35.0),),
            layout_evidence=_layout(),
        )
        for page in range(1, 4)
    )

    result = DocumentNormalizer().normalize(document(*items))

    assert result.items == ()
    assert result.metadata.statistics.footers_suppressed == 3
    assert {decision.role for decision in result.page_furniture_decisions} == {"page_footer"}


def test_list_hierarchy_is_reconstructed_from_horizontal_indentation() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="list",
                sequence_number=0,
                original_label="list_item",
                items=(
                    ExtractedListItem(
                        id="parent",
                        text="defines:",
                        marker="-",
                        source_evidence=(
                            evidence(1, 100).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=20,
                                        top=100,
                                        right=100,
                                        bottom=120,
                                    )
                                }
                            ),
                        ),
                    ),
                    ExtractedListItem(
                        id="child-a",
                        text="a process",
                        marker="-",
                        source_evidence=(
                            evidence(1, 125).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=40,
                                        top=125,
                                        right=100,
                                        bottom=145,
                                    )
                                }
                            ),
                        ),
                    ),
                    ExtractedListItem(
                        id="child-b",
                        text="a systematic process",
                        marker="-",
                        source_evidence=(
                            evidence(1, 150).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=40,
                                        top=150,
                                        right=100,
                                        bottom=170,
                                    )
                                }
                            ),
                        ),
                    ),
                    ExtractedListItem(
                        id="sibling",
                        text="does not define:",
                        marker="-",
                        source_evidence=(
                            evidence(1, 175).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=20,
                                        top=175,
                                        right=100,
                                        bottom=195,
                                    )
                                }
                            ),
                        ),
                    ),
                ),
            )
        )
    )

    normalized = result.items[0]
    assert isinstance(normalized, NormalizedList)
    assert [item.text for item in normalized.items] == ["defines:", "does not define:"]
    assert [child.text for child in normalized.items[0].children] == [
        "a process",
        "a systematic process",
    ]
    assert normalized.items[0].depth == 0
    assert normalized.items[0].children[0].depth == 1
    assert normalized.source_item_ids == ("parent", "child-a", "child-b", "sibling")


def test_list_hierarchy_clamps_skipped_indentation_levels() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="list",
                sequence_number=0,
                items=(
                    ExtractedListItem(
                        id="parent",
                        text="Parent",
                        marker="-",
                        source_evidence=(
                            evidence(1, 100).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=20,
                                        top=100,
                                        right=100,
                                        bottom=120,
                                    )
                                }
                            ),
                        ),
                    ),
                    ExtractedListItem(
                        id="deep-child",
                        text="Deep child",
                        marker="-",
                        source_evidence=(
                            evidence(1, 125).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=60,
                                        top=125,
                                        right=120,
                                        bottom=145,
                                    )
                                }
                            ),
                        ),
                    ),
                    ExtractedListItem(
                        id="middle-level",
                        text="Later middle level",
                        marker="-",
                        source_evidence=(
                            evidence(1, 150).model_copy(
                                update={
                                    "bounding_box": BoundingBox(
                                        left=40,
                                        top=150,
                                        right=120,
                                        bottom=170,
                                    )
                                }
                            ),
                        ),
                    ),
                ),
            )
        )
    )

    normalized = result.items[0]
    assert isinstance(normalized, NormalizedList)
    assert [item.text for item in normalized.items] == ["Parent"]
    assert [child.text for child in normalized.items[0].children] == [
        "Deep child",
        "Later middle level",
    ]
    assert all(child.depth == 1 for child in normalized.items[0].children)


def test_list_hierarchy_remains_flat_without_reliable_indentation() -> None:
    result = DocumentNormalizer().normalize(
        document(
            ExtractedList(
                id="list",
                sequence_number=0,
                items=(
                    ExtractedListItem(id="a", text="First", marker="-"),
                    ExtractedListItem(id="b", text="Second", marker="-"),
                ),
            )
        )
    )

    normalized = result.items[0]
    assert isinstance(normalized, NormalizedList)
    assert len(normalized.items) == 2
    assert all(not item.children for item in normalized.items)


def test_transformation_ledger_records_mapping_and_text_merge() -> None:
    source = document(
        ExtractedText(
            id="a",
            sequence_number=0,
            text="First fragment",
            source_evidence=(evidence(1),),
        ),
        ExtractedText(
            id="b",
            sequence_number=1,
            text="continues.",
            source_evidence=(evidence(1),),
        ),
    )

    result = DocumentNormalizer().normalize(source)
    events = result.transformation_ledger.events

    assert [event.stage for event in events[:2]] == ["mapping", "mapping"]
    merge = next(event for event in events if event.stage == "text_merge")
    assert merge.rule_id == "normalize.text.merge-continuation"
    assert merge.source_item_ids == ("a", "b")
    assert merge.output_item_ids
    assert merge.id.startswith("tx:")


def test_transformation_ledger_records_suppression_reason() -> None:
    source = document(
        ExtractedText(
            id="page-number",
            sequence_number=0,
            text="12",
            source_evidence=(evidence(1),),
        )
    )

    result = DocumentNormalizer().normalize(source)
    event = result.transformation_ledger.events[0]

    assert event.stage == "selection"
    assert event.action == "suppress"
    assert event.source_item_ids == ("page-number",)
    assert event.details["reason"] == "page_number"


def test_transformation_ledger_is_deterministic() -> None:
    source = document(
        ExtractedText(
            id="a",
            sequence_number=0,
            text="Text.",
            source_evidence=(evidence(1),),
        )
    )

    first = DocumentNormalizer().normalize(source).transformation_ledger
    second = DocumentNormalizer().normalize(source).transformation_ledger

    assert first == second
    assert first.events[0].id == second.events[0].id
