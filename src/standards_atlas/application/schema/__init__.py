"""Bounded schema-contract compatibility support."""

from .baseline import (
    SCHEMA_BASELINES,
    SCHEMA_POLICIES,
    SchemaBaseline,
    require_current_schema,
    require_supported_schema,
)
from .inventory import (
    VERSIONED_INTERFACES,
    LifecycleBoundary,
    VersionAxis,
    VersionedInterface,
    schema_managed_interfaces,
)
from .policy import (
    CURRENT_COMPATIBILITY_PHASE,
    STABLE_READER_WINDOW,
    CompatibilityPhase,
    SchemaDeprecationWarning,
    SchemaPolicy,
)

__all__ = [
    "CURRENT_COMPATIBILITY_PHASE",
    "SCHEMA_BASELINES",
    "SCHEMA_POLICIES",
    "STABLE_READER_WINDOW",
    "VERSIONED_INTERFACES",
    "CompatibilityPhase",
    "LifecycleBoundary",
    "SchemaBaseline",
    "SchemaDeprecationWarning",
    "SchemaPolicy",
    "VersionAxis",
    "VersionedInterface",
    "require_current_schema",
    "require_supported_schema",
    "schema_managed_interfaces",
]
