"""Standard model for Standards Atlas."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from standards_atlas.domain.model.document import DocumentType, EngineeringDocument
from standards_atlas.domain.model.identifiers import StandardKey


class Standard(EngineeringDocument):
    """A technical standard represented in Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    key: StandardKey
    title: str = Field(min_length=1)
    document_type: DocumentType = DocumentType.STANDARD

    name: str = Field(min_length=1)
    parent_key: StandardKey | None = None

    @classmethod
    def from_name(
        cls,
        *,
        key: StandardKey,
        name: str,
        year: int | None = None,
        parent_key: StandardKey | None = None,
    ) -> Standard:
        return cls(
            key=key,
            title=name,
            name=name,
            year=year,
            parent_key=parent_key,
        )
