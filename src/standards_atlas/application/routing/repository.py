"""Ports for loading routing contracts and persisting routing artifacts."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.application.routing.model import (
    DocumentRoutingArtifact,
    RoutingContract,
)


class RoutingContractRepository(Protocol):
    """Load one immutable routing contract by stable identity and version."""

    def load(self, contract_id: str, version: str) -> RoutingContract: ...


class SemanticRoutingArtifactRepository(Protocol):
    """Persist deterministic per-document routing results."""

    def save(self, artifact: DocumentRoutingArtifact) -> None: ...

    def load(
        self,
        document_key: str,
        contract_id: str,
        contract_version: str,
    ) -> DocumentRoutingArtifact: ...
