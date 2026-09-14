"""Opt-in schema guards for concrete application/adapter serialization contracts.

No domain dependency, automatic family inference, version replacement or fingerprint
normalization. Unversioned nested models can share this base without acquiring a
new lifecycle contract. Dict envelopes still require an explicit writer guard.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import (
    BaseModel,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from .baseline import require_current_schema, require_supported_schema


class SchemaBoundModel(BaseModel):
    """Bind a model's actual marker to the registry at input and serialization time."""

    SCHEMA_FAMILY: ClassVar[str | None] = None

    @model_validator(mode="before")
    @classmethod
    def explicit_json_schema_marker(cls, value: Any, info: ValidationInfo) -> Any:
        # JSON is a serialized read, not a constructor for a new object. This also
        # covers nested registered models without changing Python builder defaults.
        if (
            cls.SCHEMA_FAMILY is not None
            and info.mode == "json"
            and (not isinstance(value, dict) or "schema_version" not in value)
        ):
            raise ValueError(f"{cls.SCHEMA_FAMILY} JSON input requires an explicit schema_version")
        return value

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def registered_schema_marker(cls, value: Any) -> Any:
        if cls.SCHEMA_FAMILY is not None:
            require_supported_schema(cls.SCHEMA_FAMILY, value)
        return value

    @model_serializer(mode="wrap")
    def current_schema_serialization(self, handler: SerializerFunctionWrapHandler):
        # Intentionally no return annotation: Any/dict would erase Pydantic's
        # delegated serialization schema, although the payload is unchanged.
        family = type(self).SCHEMA_FAMILY
        if family is not None:
            # Use the class binding, never an instance shadow introduced by an
            # unchecked copy. Inspect the actual marker, not a default or view.
            require_current_schema(family, getattr(self, "schema_version", None))
        return handler(self)
