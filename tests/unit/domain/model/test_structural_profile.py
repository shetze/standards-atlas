import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference
from standards_atlas.domain.model.structural_profile import (
    AnnexStatus,
    CanonicalDocumentSection,
    DomainCategory,
    StructuralProfile,
)


def test_profile_combines_independent_document_and_domain_taxonomies() -> None:
    profile = StructuralProfile(
        canonical_section=CanonicalDocumentSection.BODY,
        document_categories=(
            DomainCategory(taxonomy="document.polarion-export", category="work_item"),
        ),
        domain_categories=(
            DomainCategory(taxonomy="domain.functional-safety", category="verification"),
            DomainCategory(taxonomy="domain.cybersecurity", category="validation_and_assurance"),
        ),
    )

    assert profile.document_categories[0].category == "work_item"
    assert len(profile.domain_categories) == 2


def test_annex_status_is_only_valid_for_annexes() -> None:
    with pytest.raises(ValidationError, match="annex_status requires"):
        StructuralProfile(
            canonical_section=CanonicalDocumentSection.BODY,
            annex_status=AnnexStatus.NORMATIVE,
        )


def test_clause_accepts_optional_structural_profile() -> None:
    profile = StructuralProfile(canonical_section=CanonicalDocumentSection.SCOPE)
    clause = Clause(
        id=ClauseId(value="DOC-1"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.SCOPE,
        structural_profile=profile,
    )

    assert clause.structural_profile == profile
    assert (
        Clause(
            id=ClauseId(value="DOC-2"),
            reference=StandardReference(standard="DOC", clause="2"),
            clause_type=ClauseType.CLAUSE,
        ).structural_profile
        is None
    )


def test_profile_accepts_open_label_with_optional_canonical_semantic_section_role() -> None:
    from standards_atlas.domain.model.structural_profile import SemanticSection

    profile = StructuralProfile(
        semantic_sections=(SemanticSection(label="Tool support", start_offset=0, end_offset=12),)
    )

    assert profile.semantic_sections[0].label == "Tool support"
    assert profile.semantic_sections[0].role is None
