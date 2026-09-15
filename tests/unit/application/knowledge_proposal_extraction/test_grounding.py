import hashlib

from standards_atlas.application.knowledge_proposal_extraction import ground_evidence_quote
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
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
    assert result.anchor.clause_id == clause.id


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
