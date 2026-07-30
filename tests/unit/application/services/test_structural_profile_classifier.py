from standards_atlas.application.services.structural_profile_classifier import (
    StructuralProfileClassifier,
    StructuralProfileContext,
)
from standards_atlas.domain.model.structural_profile import (
    AnnexStatus,
    CanonicalDocumentSection,
)


def test_classifier_preserves_explicit_normative_annex_status() -> None:
    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="A", heading="Annex A (normative) Test methods")
    )

    assert profile.canonical_section == CanonicalDocumentSection.ANNEX
    assert profile.annex_status == AnnexStatus.NORMATIVE


def test_classifier_does_not_assume_iec_main_body_for_unknown_document_heading() -> None:
    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(
            reference="WI-42",
            heading="Software safety requirement",
            document_taxonomy="document.polarion-export",
            document_category="requirement",
            domain_taxonomy="domain.functional-safety",
            domain_category="software_development",
        )
    )

    assert profile.canonical_section is None
    assert profile.document_categories[0].category == "requirement"
    assert profile.domain_categories[0].category == "software_development"


def test_numeric_clause_is_classified_as_body() -> None:
    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="6.4.2", heading="Verification")
    )

    assert profile.canonical_section is CanonicalDocumentSection.BODY
