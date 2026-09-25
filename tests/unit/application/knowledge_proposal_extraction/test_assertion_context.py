from standards_atlas.application.knowledge_proposal_extraction import assertion_cbox_context
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


def _clause(
    clause_id: str,
    reference: str,
    heading: str,
    *,
    parent: str | None = None,
    text: str = "",
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="TEST", clause=reference),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"{clause_id}-text", text=text),) if text else (),
    )


def test_assertion_cbox_projects_associative_leading_context_for_empty_groups() -> None:
    root = _clause("root", "0", "Test document")
    section = _clause(
        "s12",
        "12",
        "Guidance for system development with safety-related availability requirements",
        parent="root",
    )
    introduction = _clause(
        "s121",
        "12.1",
        "Introduction",
        parent="s12",
        text="Section 12 introduction establishes the availability guidance context.",
    )
    analysis = _clause(
        "s123",
        "12.3",
        "Availability considerations during hardware design phase",
        parent="s12",
    )
    quantitative = _clause(
        "s1231",
        "12.3.1",
        "Random hardware fault quantitative analysis",
        parent="s123",
    )
    method = _clause(
        "s12311",
        "12.3.1.1",
        "Emergency Operation Tolerance Time Interval calculation method",
        parent="s1231",
        text="The Emergency Operation Tolerance Time Interval is calculated using the PMHF.",
    )
    target = _clause(
        "s12313",
        "12.3.1.3",
        "Emergency Operation Time Interval calculation if no PMHF value is available",
        parent="s1231",
        text="If the method is used, the criteria are applicable.",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=(root, section, introduction, analysis, quantitative, method, target),
    )

    context = assertion_cbox_context(document, target)

    assert context["canonical_cbox_version"] == "1.2"
    assert context["associative_context"] == [
        {
            "clause_id": "s12311",
            "reference": "12.3.1.1",
            "heading": "Emergency Operation Tolerance Time Interval calculation method",
            "text": "The Emergency Operation Tolerance Time Interval is calculated using the PMHF.",
            "role": "leading_substantive_descendant",
            "via_ancestor_clause_id": "s1231",
            "via_ancestor_reference": "12.3.1",
            "via_ancestor_heading": "Random hardware fault quantitative analysis",
        },
        {
            "clause_id": "s121",
            "reference": "12.1",
            "heading": "Introduction",
            "text": "Section 12 introduction establishes the availability guidance context.",
            "role": "leading_substantive_descendant",
            "via_ancestor_clause_id": "s12",
            "via_ancestor_reference": "12",
            "via_ancestor_heading": (
                "Guidance for system development with safety-related availability requirements"
            ),
        },
    ]


def test_assertion_cbox_projects_text_bearing_ancestor_as_associative_context() -> None:
    parent = _clause(
        "parent",
        "7.4",
        "Software design and development",
        text="This subclause introduces the software design activity.",
    )
    child = _clause(
        "child",
        "7.4.1",
        "Detailed requirement",
        parent="parent",
        text="The implementation shall satisfy the requirement.",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=(parent, child),
    )

    context = assertion_cbox_context(document, child)

    assert context["associative_context"] == [
        {
            "clause_id": "parent",
            "reference": "7.4",
            "heading": "Software design and development",
            "text": "This subclause introduces the software design activity.",
            "role": "ancestor_body",
            "via_ancestor_clause_id": "parent",
            "via_ancestor_reference": "7.4",
            "via_ancestor_heading": "Software design and development",
        }
    ]


def test_first_substantive_leaf_does_not_receive_its_own_body_as_associative_context() -> None:
    parent = _clause("parent", "5", "Heading-only group")
    first = _clause(
        "first",
        "5.1",
        "First substantive leaf",
        parent="parent",
        text="This is the first substantive body.",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=(parent, first),
    )

    context = assertion_cbox_context(document, first)

    assert context["associative_context"] == []
