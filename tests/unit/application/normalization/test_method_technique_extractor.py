from standards_atlas.application.model import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedList,
    ExtractedListItem,
    ExtractedTable,
    ExtractionMetadata,
    MethodTechniqueKind,
)
from standards_atlas.application.normalization import DocumentNormalizer
from standards_atlas.domain.model import TableCell, TableRow


def _document(*items):
    return ExtractedDocument(
        source_id="sample",
        items=items,
        metadata=ExtractionMetadata(converter="docling"),
    )


def test_methods_are_extracted_from_list_under_signalled_heading() -> None:
    result = DocumentNormalizer().normalize(
        _document(
            ExtractedHeading(
                id="heading",
                sequence_number=0,
                text="Recommended methods",
                observed_level=2,
            ),
            ExtractedList(
                id="list",
                sequence_number=1,
                items=(
                    ExtractedListItem(text="Failure mode and effects analysis (FMEA)"),
                    ExtractedListItem(text="Fault tree analysis (FTA)"),
                ),
            ),
        )
    )

    assert [candidate.name for candidate in result.method_technique_candidates] == [
        "Failure mode and effects analysis (FMEA)",
        "Fault tree analysis (FTA)",
    ]
    assert all(
        candidate.kind == MethodTechniqueKind.METHOD
        for candidate in result.method_technique_candidates
    )
    assert result.metadata.statistics.method_technique_candidates == 2


def test_techniques_are_extracted_from_signalled_table() -> None:
    result = DocumentNormalizer().normalize(
        _document(
            ExtractedTable(
                id="table",
                sequence_number=0,
                caption="Software test techniques",
                rows=(
                    TableRow(
                        cells=(
                            TableCell(text="Technique", is_header=True),
                            TableCell(text="Recommendation", is_header=True),
                        )
                    ),
                    TableRow(
                        cells=(
                            TableCell(text="Boundary value analysis"),
                            TableCell(text="HR"),
                        )
                    ),
                ),
            )
        )
    )

    candidate = result.method_technique_candidates[0]
    assert candidate.name == "Boundary value analysis"
    assert candidate.kind == MethodTechniqueKind.TECHNIQUE
    assert candidate.extraction_rule == "methods.signalled-table-row"


def test_unrelated_lists_are_not_registered() -> None:
    result = DocumentNormalizer().normalize(
        _document(
            ExtractedHeading(
                id="heading",
                sequence_number=0,
                text="General requirements",
                observed_level=2,
            ),
            ExtractedList(
                id="list",
                sequence_number=1,
                items=(ExtractedListItem(text="The supplier shall document the result."),),
            ),
        )
    )

    assert result.method_technique_candidates == ()
