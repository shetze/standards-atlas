"""Execution policy for persisted deterministic routing decisions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.routing.model import RoutingDecision, RoutingDisposition

_DISPOSITION_RANK = {
    RoutingDisposition.SKIP: 0,
    RoutingDisposition.OPTIONAL: 1,
    RoutingDisposition.PREFERRED: 2,
    RoutingDisposition.REQUIRED: 3,
}


class RoutingExecutionPolicy(BaseModel):
    """Decide whether one routed semantic task should execute."""

    model_config = ConfigDict(frozen=True)

    minimum_disposition: RoutingDisposition = RoutingDisposition.OPTIONAL
    include_unrouted: bool = False

    def allows(self, decision: RoutingDecision | None) -> bool:
        """Return whether a routing decision satisfies the execution threshold."""

        if decision is None:
            return self.include_unrouted
        return (
            _DISPOSITION_RANK[decision.disposition] >= _DISPOSITION_RANK[self.minimum_disposition]
        )
