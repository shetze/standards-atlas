"""Ports for loading versioned deterministic routing contracts."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.application.routing.model import RoutingContract


class RoutingContractRepository(Protocol):
    """Load one immutable routing contract by stable identity and version."""

    def load(self, contract_id: str, version: str) -> RoutingContract: ...
