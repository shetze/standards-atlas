import hashlib

from standards_atlas.application.knowledge_proposal_extraction import ground_evidence_quote
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    EvidenceSourceKind,
    KnowledgeProposalViolationKind,
    StandardReference,
    TextBlock,
)


def _clause(text: str) -> Clause:
    return Clause(
        id=ClauseId(value="g-1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="t-1", text=text),),
    )


def test_unique_exact_quote_creates_text_safe_anchor() -> None:
    clause = _clause("The verification plan shall specify the verification criteria.")
    quote = "verification plan shall specify the verification criteria"

    result = ground_evidence_quote(clause, quote)

    assert result.resolved
    assert result.violation_kind is None
    assert result.anchor is not None
    assert clause.plain_text[result.anchor.start_offset : result.anchor.end_offset] == quote
    assert result.anchor.content_hash == hashlib.sha256(quote.encode("utf-8")).hexdigest()
    assert result.anchor.source_clause_id == clause.id
    assert result.anchor.source_kind is EvidenceSourceKind.BODY


def test_missing_quote_is_unresolved_without_fuzzy_fallback() -> None:
    result = ground_evidence_quote(_clause("Verification shall be performed."), "verification")

    assert not result.resolved
    assert result.anchor is None
    assert result.violation_kind is KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING


def test_repeated_quote_is_ambiguous_instead_of_selecting_first_match() -> None:
    result = ground_evidence_quote(
        _clause("Verification is required. Verification shall be recorded."),
        "Verification",
    )

    assert not result.resolved
    assert result.anchor is None
    assert result.violation_kind is KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING


def test_heading_quote_can_be_grounded_on_local_heading() -> None:
    clause = Clause(
        id=ClauseId(value="g-heading"),
        reference=StandardReference(standard="TEST", clause="2"),
        clause_type=ClauseType.CLAUSE,
        heading="Emergency Operation Time Interval calculation if no PMHF value is available",
        content=(TextBlock(id="t-2", text="If the method is used, the criteria apply."),),
    )

    result = ground_evidence_quote(
        clause,
        "Emergency Operation Time Interval calculation if no PMHF value is available",
        source_kind=EvidenceSourceKind.HEADING,
        source_clause_id=clause.id,
    )

    assert result.resolved
    assert result.anchor is not None
    assert result.anchor.source_clause_id == clause.id
    assert result.anchor.source_kind is EvidenceSourceKind.HEADING
    assert result.anchor.start_offset == 0
    assert result.anchor.end_offset == len(clause.heading or "")


def test_ancestor_heading_quote_uses_canonical_cbox_source_identity() -> None:
    clause = _clause("If the method is used, the criteria apply.")
    ancestor_id = ClauseId(value="g-parent")
    result = ground_evidence_quote(
        clause,
        "Random hardware fault quantitative analysis",
        source_kind=EvidenceSourceKind.HEADING,
        source_clause_id=ancestor_id,
        semantic_context={
            "ancestor_headings": [
                {
                    "clause_id": ancestor_id.value,
                    "reference": "12.3.1",
                    "heading": "Random hardware fault quantitative analysis",
                }
            ]
        },
    )

    assert result.resolved
    assert result.anchor is not None
    assert result.anchor.source_clause_id == ancestor_id
    assert result.anchor.source_kind is EvidenceSourceKind.HEADING


def test_body_quote_cannot_be_grounded_on_ancestor_clause() -> None:
    clause = _clause("If the method is used, the criteria apply.")
    result = ground_evidence_quote(
        clause,
        "parent body",
        source_kind=EvidenceSourceKind.BODY,
        source_clause_id=ClauseId(value="g-parent"),
    )

    assert not result.resolved
    assert result.reason == "body evidence must belong to the currently extracted clause"
