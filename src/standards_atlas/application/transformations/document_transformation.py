"""Transformation port for engineering documents."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument


class DocumentTransformation(Protocol):
    """A transformation that derives an improved EngineeringDocument."""

    def transform(self, document: EngineeringDocument) -> EngineeringDocument:
        """Transform an engineering document."""
        ...
