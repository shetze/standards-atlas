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


def test_classifier_does_not_assume_document_or_domain_taxonomy() -> None:
    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="WI-42", heading="Software safety requirement")
    )

    assert profile.canonical_section is None
    assert profile.document_categories == ()
    assert profile.domain_categories == ()


def test_numeric_clause_is_classified_as_body() -> None:
    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="6.4.2", heading="Verification")
    )

    assert profile.canonical_section is CanonicalDocumentSection.BODY


def test_classifier_detects_labelled_semantic_sections_in_clause_text() -> None:
    text = (
        "Aim: Establish the intended objective.\n"
        "Description: The technique analyses the control flow.\n"
        "References: IEC 61508-7."
    )

    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="C.2.6.1", heading="Control flow analysis", text=text)
    )

    assert [section.role.value for section in profile.semantic_sections] == [
        "aim",
        "description",
        "references",
    ]
    labels = [
        text[section.start_offset : section.end_offset].split(":", 1)[0].strip()
        for section in profile.semantic_sections
    ]
    assert labels == ["Aim", "Description", "References"]


def test_classifier_detects_inline_labelled_sections_after_sentence_boundary() -> None:
    text = "Aim: Do X. Description: Explain Y. References: ISO 1234."

    profile = StructuralProfileClassifier().classify(
        StructuralProfileContext(reference="B.4.3", heading="Technique", text=text)
    )

    assert tuple(section.role.value for section in profile.semantic_sections) == (
        "aim",
        "description",
        "references",
    )
