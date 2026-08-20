"""Load versioned routing contracts from packaged YAML resources."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from standards_atlas.application.routing.model import RoutingContract
from standards_atlas.application.schema import require_supported_schema


class ResourceRoutingContractRepository:
    """Resolve immutable routing-contract resources shipped with the package."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def load(self, contract_id: str, version: str) -> RoutingContract:
        if self._root is None:
            resource = (
                files("standards_atlas.resources")
                / "routing-contracts"
                / contract_id
                / version
                / "routing.yaml"
            )
            if not resource.is_file():
                raise KeyError(f"routing contract not found: {contract_id}@{version}")
            payload = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
        else:
            path = self._root / contract_id / version / "routing.yaml"
            if not path.is_file():
                raise KeyError(f"routing contract not found: {contract_id}@{version}")
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        require_supported_schema("routing-contract-resource", payload.get("schema_version"))
        contract_payload = {key: value for key, value in payload.items() if key != "schema_version"}
        contract = RoutingContract.model_validate(contract_payload)
        if contract.id != contract_id or contract.version != version:
            raise ValueError(
                "routing contract resource identity mismatch: "
                f"expected {contract_id}@{version}, got {contract.id}@{contract.version}"
            )
        return contract
