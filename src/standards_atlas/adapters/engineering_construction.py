"""Persistence for deterministic EngineeringDocument construction contracts."""

from __future__ import annotations

import os
from pathlib import Path

from standards_atlas.adapters.normalization import canonical_json
from standards_atlas.application.model.engineering_construction import (
    EngineeringConstructionContract,
)


class EngineeringConstructionContractRepository:
    """Store the construction proof next to the canonical document artifacts."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "construction"

    def path(self, document_key: str) -> Path:
        key = document_key.strip()
        if not key or key in {".", ".."} or Path(key).is_absolute():
            raise ValueError("Document key must not contain path components")
        if "/" in key or "\\" in key:
            raise ValueError("Document key must not contain path components")
        path = (self._root / key / "contract.json").resolve()
        if not path.is_relative_to(self._workspace):
            raise ValueError("Construction contracts must remain below the workspace")
        return path

    def save(
        self,
        document_key: str,
        contract: EngineeringConstructionContract,
    ) -> Path:
        path = self.path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(canonical_json(contract), encoding="utf-8")
        os.replace(temporary, path)
        return path

    def load(self, document_key: str) -> EngineeringConstructionContract:
        return EngineeringConstructionContract.model_validate_json(
            self.path(document_key).read_text(encoding="utf-8")
        )
