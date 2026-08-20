"""Typed workflow manifest binding for versioned routing contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.schema import require_supported_schema


class RoutingContractReference(BaseModel):
    """Stable identity of one packaged routing contract resource."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RoutingContractManifest(BaseModel):
    """Workflow manifest selecting one concrete routing contract."""

    model_config = ConfigDict(frozen=True)

    manifest_type: Literal["routing_contract"] = "routing_contract"
    schema_version: Literal[1] = 1
    contract: RoutingContractReference


def load_routing_contract_manifest(path: Path) -> RoutingContractManifest:
    """Load and validate one routing-contract workflow manifest."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    require_supported_schema("routing-contract-manifest", payload.get("schema_version"))
    return RoutingContractManifest.model_validate(payload)
