"""Bounded schema-contract compatibility support."""

from .baseline import (
    SCHEMA_BASELINES,
    SCHEMA_POLICIES,
    SchemaBaseline,
    require_current_schema,
    require_supported_schema,
)
from .policy import SchemaDeprecationWarning, SchemaPolicy

__all__ = [
    "SCHEMA_BASELINES",
    "SCHEMA_POLICIES",
    "SchemaBaseline",
    "SchemaDeprecationWarning",
    "SchemaPolicy",
    "require_current_schema",
    "require_supported_schema",
]
