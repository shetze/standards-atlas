from standards_atlas.application.services.semantic_role_classifier import (
    SemanticRoleClassification,
    SemanticRoleClassifier,
    SemanticRoleContext,
    SemanticRoleEvidence,
)
from standards_atlas.domain.model.semantic_role import SemanticRole


def test_classifies_exact_heading() -> None:
    result = SemanticRoleClassifier().classify(
        SemanticRoleContext(reference="5.1.2", heading="Requirements")
    )
    assert result.roles == (SemanticRole.REQUIREMENTS,)
    assert result.confidence == 1.0
    assert result.evidence[0].kind == "heading_exact"


def test_classifies_composed_heading_with_multiple_roles() -> None:
    result = SemanticRoleClassifier().classify(
        SemanticRoleContext(
            reference="6.4",
            heading="Application validation and assessment",
        )
    )
    assert result.roles == (
        SemanticRole.VALIDATION,
        SemanticRole.ASSESSMENT,
    )
    assert result.confidence == 0.86


def test_term_ancestor_has_precedence_over_local_keyword() -> None:
    result = SemanticRoleClassifier().classify(
        SemanticRoleContext(
            reference="3.56",
            heading="requirement",
            ancestor_roles=(SemanticRole.TERMS_AND_DEFINITIONS,),
        )
    )
    assert result.roles == (SemanticRole.TERMS_AND_DEFINITIONS,)
    assert result.evidence[0].kind == "ancestor_role"


def test_annex_role_uses_reference_and_status() -> None:
    result = SemanticRoleClassifier().classify(
        SemanticRoleContext(
            reference="D.1",
            heading="Bibliography of techniques",
            annex_status="informative",
        )
    )
    assert result.roles == (SemanticRole.ANNEX,)
    assert {item.kind for item in result.evidence} == {
        "annex_reference",
        "annex_status",
    }


def test_unclassified_heading_remains_empty() -> None:
    result = SemanticRoleClassifier().classify(
        SemanticRoleContext(reference="5.1", heading="General")
    )
    assert result.roles == ()
    assert result.confidence == 0.0


class _Extension:
    def classify(self, context: SemanticRoleContext) -> SemanticRoleClassification:
        assert context.heading == "General"
        return SemanticRoleClassification(
            roles=(SemanticRole.REQUIREMENTS,),
            confidence=0.75,
            evidence=(SemanticRoleEvidence("llm", "content", 0.75),),
            classifier="llm",
        )


def test_optional_extension_is_used_only_for_low_confidence_results() -> None:
    classifier = SemanticRoleClassifier(_Extension(), fallback_threshold=0.8)
    result = classifier.classify(SemanticRoleContext(reference="5.1", heading="General"))
    assert result.classifier == "llm"
    assert result.roles == (SemanticRole.REQUIREMENTS,)


def test_optional_extension_does_not_replace_exact_result() -> None:
    classifier = SemanticRoleClassifier(_Extension(), fallback_threshold=0.8)
    result = classifier.classify(SemanticRoleContext(reference="5.1.2", heading="Requirements"))
    assert result.classifier == "deterministic"
    assert result.confidence == 1.0
