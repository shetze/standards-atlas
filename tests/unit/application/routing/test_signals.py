from standards_atlas.application.routing import taxonomy_signal_profile
from standards_atlas.domain.model.structural_profile import (
    AnnexStatus,
    CanonicalDocumentSection,
    DomainCategory,
    StructuralProfile,
)


def test_structural_profile_projection_preserves_namespaced_taxonomy_evidence() -> None:
    source = StructuralProfile(
        canonical_section=CanonicalDocumentSection.ANNEX,
        annex_status=AnnexStatus.NORMATIVE,
        document_categories=(
            DomainCategory(
                taxonomy="document.iec-directives-2",
                category="supplementary_elements",
                version="1.0.0",
            ),
        ),
        domain_categories=(
            DomainCategory(
                taxonomy="domain.functional-safety",
                category="verification",
                version="1.0.0",
            ),
        ),
    )

    result = taxonomy_signal_profile(
        source,
        heading="Annex A verification",
        node_kind="leaf",
        content_profile="text_dominant",
    )

    assert result.canonical_section == "annex"
    assert result.annex_status == "normative"
    assert result.document_categories[0].taxonomy == "document.iec-directives-2"
    assert result.domain_categories[0].category == "verification"
    assert result.heading == "Annex A verification"
    assert result.node_kind == "leaf"
    assert result.content_profile == "text_dominant"
