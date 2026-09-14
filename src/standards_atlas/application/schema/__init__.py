"""Bounded schema-contract compatibility support."""

from .baseline import (
    SCHEMA_POLICIES,
    require_current_payload,
    require_current_schema,
    require_supported_schema,
    validate_schema_registry,
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
    "SCHEMA_POLICIES",
    "STABLE_READER_WINDOW",
    "VERSIONED_INTERFACES",
    "CompatibilityPhase",
    "LifecycleBoundary",
    "SchemaDeprecationWarning",
    "SchemaPolicy",
    "VersionAxis",
    "VersionedInterface",
    "require_current_payload",
    "require_current_schema",
    "require_supported_schema",
    "schema_managed_interfaces",
    "validate_schema_registry",
]
