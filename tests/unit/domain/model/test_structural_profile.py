import pytest
from pydantic import ValidationError

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
