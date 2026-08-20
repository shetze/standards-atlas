from pathlib import Path

import pytest

from standards_atlas.adapters.routing_contracts import ResourceRoutingContractRepository
from standards_atlas.application.routing import RoutingDisposition, TaxonomyCategoryScope


def test_packaged_repository_loads_versioned_contract() -> None:
    contract = ResourceRoutingContractRepository().load(
        "functional-safety-semantic-profile",
        "1.0.0",
    )

    assert contract.id == "functional-safety-semantic-profile"
    assert contract.version == "1.0.0"
    assert contract.taxonomy_requirements[0].scope is TaxonomyCategoryScope.DOMAIN
    assert contract.taxonomy_requirements[0].taxonomy == "domain.functional-safety"
    assert contract.tasks[0].id == "semantic-profile-classification"
    assert contract.tasks[0].version == "2.2.0"
    assert contract.rules[0].effect is RoutingDisposition.REQUIRED


def test_repository_rejects_resource_identity_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "expected" / "1.0.0"
    path.mkdir(parents=True)
    (path / "routing.yaml").write_text(
        """schema_version: 1
id: wrong
version: 1.0.0
tasks:
  - id: task
    version: 1.0.0
rules:
  - id: rule
    task: task
    effect: required
    when:
      kind: always
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity mismatch"):
        ResourceRoutingContractRepository(tmp_path).load("expected", "1.0.0")


def test_repository_rejects_undeclared_rule_task(tmp_path: Path) -> None:
    path = tmp_path / "contract" / "1.0.0"
    path.mkdir(parents=True)
    (path / "routing.yaml").write_text(
        """schema_version: 1
id: contract
version: 1.0.0
tasks:
  - id: task-a
    version: 1.0.0
rules:
  - id: rule
    task: task-b
    effect: required
    when:
      kind: always
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="undeclared tasks: task-b"):
        ResourceRoutingContractRepository(tmp_path).load("contract", "1.0.0")
