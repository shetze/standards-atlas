"""Identifier value objects for the Standards Atlas domain model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DocumentKey(BaseModel):
    """Stable key identifying an engineering document inside Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)


class StandardKey(BaseModel):
    """Stable key identifying a standard inside Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)


class ClauseId(BaseModel):
    """Stable internal identifier for a clause."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)


class StandardReference(BaseModel):
    """Human-readable reference to a clause in a standard."""

    model_config = ConfigDict(frozen=True)

    standard: str = Field(min_length=1)
    part: str | None = None
    year: int | None = None
    clause: str = Field(min_length=1)

    def as_text(self) -> str:
        standard = f"{self.standard}-{self.part}" if self.part else self.standard
        if self.year is None:
            return f"{standard} {self.clause}"
        return f"{standard}:{self.year} {self.clause}"


class AnnotationId(BaseModel):
    """Stable identifier for a clause annotation."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)
