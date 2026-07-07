"""Standard model for Standards Atlas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.clause import Clause
from standards_atlas.domain.model.identifiers import StandardKey


class Standard(BaseModel):
    """A technical standard represented in Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    key: StandardKey
    name: str = Field(min_length=1)
    year: int | None = None
    parent_key: StandardKey | None = None

    clauses: tuple[Clause, ...] = ()
