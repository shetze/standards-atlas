from standards_atlas.application.routing import (
    AllMatcher,
    AlwaysMatcher,
    AnyMatcher,
    HeadingContainsMatcher,
    NotMatcher,
    SignalEqualsMatcher,
    TaxonomyCategoryMatcher,
    TaxonomyCategoryScope,
    TaxonomyCategorySignal,
    TaxonomySignalField,
    TaxonomySignalProfile,
    matches,
)


def _profile() -> TaxonomySignalProfile:
    return TaxonomySignalProfile(
        canonical_section="body",
        annex_status=None,
        document_categories=(
            TaxonomyCategorySignal(
                taxonomy="document.iec-directives-2",
                version="1.0.0",
                category="normative_technical_elements",
            ),
        ),
        domain_categories=(
            TaxonomyCategorySignal(
                taxonomy="domain.functional-safety",
                version="1.0.0",
                category="verification",
            ),
        ),
        node_kind="leaf",
        content_profile="text_dominant",
        heading="Software Verification",
    )


def test_scalar_matcher_uses_only_explicit_signal_value() -> None:
    profile = _profile()

    assert matches(
        SignalEqualsMatcher(
            field=TaxonomySignalField.CANONICAL_SECTION,
            value="body",
        ),
        profile,
    )
    assert not matches(
        SignalEqualsMatcher(
            field=TaxonomySignalField.CANONICAL_SECTION,
            value="scope",
        ),
        profile,
    )


def test_category_matcher_respects_scope_taxonomy_and_version() -> None:
    profile = _profile()

    assert matches(
        TaxonomyCategoryMatcher(
            scope=TaxonomyCategoryScope.DOMAIN,
            taxonomy="domain.functional-safety",
            version="1.0.0",
            category="verification",
        ),
        profile,
    )
    assert not matches(
        TaxonomyCategoryMatcher(
            scope=TaxonomyCategoryScope.DOCUMENT,
            taxonomy="domain.functional-safety",
            version="1.0.0",
            category="verification",
        ),
        profile,
    )
    assert not matches(
        TaxonomyCategoryMatcher(
            scope=TaxonomyCategoryScope.DOMAIN,
            taxonomy="domain.functional-safety",
            version="2.0.0",
            category="verification",
        ),
        profile,
    )


def test_category_matcher_may_accept_any_version_explicitly() -> None:
    assert matches(
        TaxonomyCategoryMatcher(
            scope=TaxonomyCategoryScope.DOMAIN,
            taxonomy="domain.functional-safety",
            category="verification",
        ),
        _profile(),
    )


def test_boolean_matchers_compose_without_free_form_expressions() -> None:
    profile = _profile()
    category = TaxonomyCategoryMatcher(
        scope=TaxonomyCategoryScope.DOMAIN,
        taxonomy="domain.functional-safety",
        category="verification",
    )
    body = SignalEqualsMatcher(
        field=TaxonomySignalField.CANONICAL_SECTION,
        value="body",
    )

    assert matches(AllMatcher(matchers=(category, body)), profile)
    assert matches(
        AnyMatcher(
            matchers=(
                SignalEqualsMatcher(
                    field=TaxonomySignalField.CANONICAL_SECTION,
                    value="scope",
                ),
                category,
            )
        ),
        profile,
    )
    assert matches(NotMatcher(matcher=NotMatcher(matcher=AlwaysMatcher())), profile)


def test_heading_contains_is_literal_and_case_insensitive_by_default() -> None:
    profile = _profile()

    assert matches(HeadingContainsMatcher(value="verification"), profile)
    assert not matches(
        HeadingContainsMatcher(value="verification", case_sensitive=True),
        profile,
    )
