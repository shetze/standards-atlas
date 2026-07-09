"""Application service for applying document transformations."""

from __future__ import annotations

from collections.abc import Iterable

from standards_atlas.application.transformations import DocumentTransformation
from standards_atlas.domain.model import EngineeringDocument


class DocumentTransformationService:
    """Apply a sequence of transformations to an EngineeringDocument."""

    def __init__(
        self,
        transformations: Iterable[DocumentTransformation],
    ) -> None:
        self._transformations = tuple(transformations)

    def transform(self, document: EngineeringDocument) -> EngineeringDocument:
        """Apply all configured transformations in order."""
        current = document

        for transformation in self._transformations:
            current = transformation.transform(current)

        return current
