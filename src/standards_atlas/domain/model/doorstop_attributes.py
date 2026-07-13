"""Doorstop-compatible attributes for clauses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DoorstopReference(BaseModel):
    """Reference associated with a Doorstop item.

    Standards Atlas uses the project-specific pattern reference extension:

    - keyword contains the human-readable clause reference
    - path contains a regular expression
    - type is set to "pattern"
    """

    model_config = ConfigDict(frozen=True)

    keyword: str | None = None
    path: str = Field(min_length=1)
    # type: str = "pattern"
    type: Literal["file", "pattern"] = "file"

    @model_validator(mode="after")
    def validate_reference(self) -> DoorstopReference:
        if self.type == "pattern" and not self.keyword:
            raise ValueError("keyword is required for Doorstop pattern references.")

        return self


class DoorstopItemAttributes(BaseModel):
    """Optional Doorstop standard attributes associated with a clause."""

    model_config = ConfigDict(frozen=True)

    active: bool | None = None
    derived: bool | None = None
    normative: bool | None = None
    reviewed: str | None = None

    links: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    rationale: str | None = None
    references: tuple[DoorstopReference, ...] = ()

    extended: dict[str, Any] = Field(default_factory=dict)
