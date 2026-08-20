"""Deterministic taxonomy-aware semantic routing contracts."""

from standards_atlas.application.routing.engine import DeterministicRoutingEngine
from standards_atlas.application.routing.matcher import matches
from standards_atlas.application.routing.model import (
    AllMatcher,
    AlwaysMatcher,
    AnyMatcher,
    HeadingContainsMatcher,
    NotMatcher,
    RoutingContract,
    RoutingDecision,
    RoutingDisposition,
    RoutingRule,
    SemanticRoutingPlan,
    SignalEqualsMatcher,
    TaxonomyCategoryMatcher,
    TaxonomyCategoryScope,
    TaxonomyCategorySignal,
    TaxonomySignalField,
    TaxonomySignalProfile,
)
from standards_atlas.application.routing.signals import taxonomy_signal_profile

__all__ = [
    "AllMatcher",
    "AlwaysMatcher",
    "AnyMatcher",
    "DeterministicRoutingEngine",
    "HeadingContainsMatcher",
    "NotMatcher",
    "RoutingContract",
    "RoutingDecision",
    "RoutingDisposition",
    "RoutingRule",
    "SemanticRoutingPlan",
    "SignalEqualsMatcher",
    "TaxonomyCategoryMatcher",
    "TaxonomyCategoryScope",
    "TaxonomyCategorySignal",
    "TaxonomySignalField",
    "TaxonomySignalProfile",
    "matches",
    "taxonomy_signal_profile",
]
