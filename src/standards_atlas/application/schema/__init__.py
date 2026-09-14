"""Bounded schema-contract compatibility support."""

from .baseline import (
    SCHEMA_POLICIES,
    require_current_payload,
    require_current_schema,
    require_supported_schema,
    validate_schema_registry,
)
from .inventory import (
    SCHEMA_ENVELOPE_DECISIONS,
    SCHEMA_ENVELOPE_MARKER_COUNTS,
    SCHEMA_MARKER_DECISIONS,
    VERSIONED_INTERFACES,
    LifecycleBoundary,
    SchemaEnvelopeDecision,
    SchemaMarkerDecision,
    SchemaMarkerDisposition,
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
    "SCHEMA_ENVELOPE_DECISIONS",
    "SCHEMA_ENVELOPE_MARKER_COUNTS",
    "SCHEMA_MARKER_DECISIONS",
    "SCHEMA_POLICIES",
    "STABLE_READER_WINDOW",
    "VERSIONED_INTERFACES",
    "CompatibilityPhase",
    "LifecycleBoundary",
    "SchemaDeprecationWarning",
    "SchemaEnvelopeDecision",
    "SchemaMarkerDecision",
    "SchemaMarkerDisposition",
    "SchemaPolicy",
    "VersionAxis",
    "VersionedInterface",
    "require_current_payload",
    "require_current_schema",
    "require_supported_schema",
    "schema_managed_interfaces",
    "validate_schema_registry",
]
