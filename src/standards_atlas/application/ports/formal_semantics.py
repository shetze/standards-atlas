"""Ports for derived formal-semantic projections."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument, FormalSemanticProjection


class FormalSemanticProjector(Protocol):
    """Project canonical document knowledge into a provider-neutral semantic graph model."""

    def project(
        self,
        document: EngineeringDocument,
        *,
        knowledge_domains: tuple[str, ...] = (),
    ) -> FormalSemanticProjection: ...


class FormalSemanticProjectionRepository(Protocol):
    """Persistence boundary for derived semantic projections."""

    def save(self, projection: FormalSemanticProjection) -> None: ...

    def load(self, document_key: str) -> FormalSemanticProjection | None: ...


class FormalSemanticSerializer(Protocol):
    """Serialize a provider-neutral projection into an external graph representation."""

    media_type: str

    def serialize(self, projection: FormalSemanticProjection) -> str: ...
