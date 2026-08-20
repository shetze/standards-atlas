from pathlib import Path

import pytest

from standards_atlas.application.routing import load_routing_contract_manifest


def test_load_routing_contract_manifest_selects_resource_identity(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text(
        """manifest_type: routing_contract
schema_version: 1
contract:
  id: functional-safety-semantic-profile
  version: 1.0.0
""",
        encoding="utf-8",
    )

    manifest = load_routing_contract_manifest(path)

    assert manifest.contract.id == "functional-safety-semantic-profile"
    assert manifest.contract.version == "1.0.0"


def test_routing_manifest_rejects_wrong_manifest_type(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text(
        """manifest_type: standards
schema_version: 1
contract:
  id: x
  version: 1
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="routing_contract"):
        load_routing_contract_manifest(path)
