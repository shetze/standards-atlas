from standards_atlas.application.semantic_qualification.applicability_semantics import (
    classify_explicit_applicability_statement,
    derive_explicit_applicability_subtype,
    detect_explicit_applicability_subtypes,
)
from standards_atlas.domain.model import ApplicabilityFunction


def test_explicit_applicability_assertions_are_detected() -> None:
    cases = (
        ("This part applies to railway software.", ApplicabilityFunction.INCLUSION),
        ("This part does not apply to medical equipment.", ApplicabilityFunction.EXCLUSION),
        (
            "If software is ASIL D, these requirements are applicable.",
            ApplicabilityFunction.APPLICABILITY_CONDITION,
        ),
        (
            "These requirements apply to all systems except prototype vehicles.",
            ApplicabilityFunction.EXCEPTION,
        ),
    )

    for text, expected in cases:
        assert classify_explicit_applicability_statement(text) is expected


def test_local_conditions_prerequisites_and_assumptions_are_not_applicability() -> None:
    cases = (
        "If software is ASIL D, perform an independent review.",
        "When validation starts, the specification shall be complete.",
        "Provided that the test passes, publish the report.",
        "Unless otherwise justified, the analysis shall be reviewed.",
        "The design assumes that the communication channel is available.",
        "Before validation starts, the specification shall be complete.",
    )

    for text in cases:
        assert classify_explicit_applicability_statement(text) is None
        assert detect_explicit_applicability_subtypes(text) == set()


def test_scope_context_without_explicit_applicability_is_not_positive() -> None:
    text = "Scope. This clause describes railway software lifecycle activities."

    assert derive_explicit_applicability_subtype(text) is None


def test_compound_distinct_applicability_subtypes_do_not_create_single_prior() -> None:
    text = "This part applies to railway software. This part does not apply to medical equipment."

    assert detect_explicit_applicability_subtypes(text) == {
        ApplicabilityFunction.INCLUSION,
        ApplicabilityFunction.EXCLUSION,
    }
    assert derive_explicit_applicability_subtype(text) is None
