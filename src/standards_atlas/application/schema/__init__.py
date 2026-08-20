"""Schema-contract support."""

from .baseline import SCHEMA_BASELINES, SchemaBaseline, require_current_schema

__all__ = ["SCHEMA_BASELINES", "SchemaBaseline", "require_current_schema"]
