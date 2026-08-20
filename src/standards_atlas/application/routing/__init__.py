"""Deterministic taxonomy-aware semantic routing contracts."""

from standards_atlas.application.routing.engine import DeterministicRoutingEngine
from standards_atlas.application.routing.manifest import (
    RoutingContractManifest,
    RoutingContractReference,
    load_routing_contract_manifest,
)
from standards_atlas.application.routing.matcher import matches
from standards_atlas.application.routing.model import (
    AllMatcher,
    AlwaysMatcher,
    AnyMatcher,
    ClauseRoutingRecord,
    DocumentRoutingArtifact,
    HeadingContainsMatcher,
    NotMatcher,
    RoutingContract,
    RoutingDecision,
    RoutingDisposition,
    RoutingRule,
    RoutingTaskReference,
    RoutingTaxonomyRequirement,
    SemanticRoutingPlan,
    SignalEqualsMatcher,
    TaxonomyCategoryMatcher,
    TaxonomyCategoryScope,
    TaxonomyCategorySignal,
    TaxonomySignalField,
    TaxonomySignalProfile,
)
from standards_atlas.application.routing.repository import (
    RoutingContractRepository,
    SemanticRoutingArtifactRepository,
)
from standards_atlas.application.routing.signals import taxonomy_signal_profile

__all__ = [
    "AllMatcher",
    "AlwaysMatcher",
    "AnyMatcher",
    "ClauseRoutingRecord",
    "DeterministicRoutingEngine",
    "DocumentRoutingArtifact",
    "HeadingContainsMatcher",
    "NotMatcher",
    "RoutingContract",
    "RoutingContractManifest",
    "RoutingContractReference",
    "RoutingContractRepository",
    "RoutingDecision",
    "RoutingDisposition",
    "RoutingRule",
    "RoutingTaskReference",
    "RoutingTaxonomyRequirement",
    "SemanticRoutingArtifactRepository",
    "SemanticRoutingPlan",
    "SignalEqualsMatcher",
    "TaxonomyCategoryMatcher",
    "TaxonomyCategoryScope",
    "TaxonomyCategorySignal",
    "TaxonomySignalField",
    "TaxonomySignalProfile",
    "load_routing_contract_manifest",
    "matches",
    "taxonomy_signal_profile",
]
