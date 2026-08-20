"""Declarative matcher evaluation for deterministic routing contracts."""

from __future__ import annotations

from standards_atlas.application.routing.model import (
    AllMatcher,
    AlwaysMatcher,
    AnyMatcher,
    HeadingContainsMatcher,
    NotMatcher,
    RoutingMatcher,
    SignalEqualsMatcher,
    TaxonomyCategoryMatcher,
    TaxonomySignalProfile,
)


def matches(matcher: RoutingMatcher, profile: TaxonomySignalProfile) -> bool:
    """Evaluate one closed matcher vocabulary against explicit taxonomy signals."""

    if isinstance(matcher, AlwaysMatcher):
        return True
    if isinstance(matcher, SignalEqualsMatcher):
        return profile.scalar(matcher.field) == matcher.value
    if isinstance(matcher, TaxonomyCategoryMatcher):
        return any(
            signal.taxonomy == matcher.taxonomy
            and signal.category == matcher.category
            and (matcher.version is None or signal.version == matcher.version)
            for signal in profile.categories(matcher.scope)
        )
    if isinstance(matcher, HeadingContainsMatcher):
        heading = profile.heading
        needle = matcher.value
        if not matcher.case_sensitive:
            heading = heading.casefold()
            needle = needle.casefold()
        return needle in heading
    if isinstance(matcher, AllMatcher):
        return all(matches(item, profile) for item in matcher.matchers)
    if isinstance(matcher, AnyMatcher):
        return any(matches(item, profile) for item in matcher.matchers)
    if isinstance(matcher, NotMatcher):
        return not matches(matcher.matcher, profile)
    raise TypeError(f"unsupported routing matcher: {type(matcher).__name__}")
