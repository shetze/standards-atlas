from pathlib import Path

import pytest

from standards_atlas.adapters.routing import FileSystemSemanticRoutingArtifactRepository
from standards_atlas.application.routing import (
    ClauseRoutingRecord,
    DocumentRoutingArtifact,
    RoutingDecision,
    RoutingDisposition,
    SemanticRoutingPlan,
    TaxonomySignalProfile,
)


def _artifact() -> DocumentRoutingArtifact:
    plan = SemanticRoutingPlan(
        contract_id="contract",
        contract_version="1.0.0",
        decisions=(
            RoutingDecision(
                task="semantic-profile-classification",
                disposition=RoutingDisposition.REQUIRED,
                matched_rules=("required",),
                reasons=("contract_rule:required",),
            ),
        ),
    )
    return DocumentRoutingArtifact(
        document_key="TEST",
        contract_id="contract",
        contract_version="1.0.0",
        clauses=(
            ClauseRoutingRecord(
                clause_id="clause-1",
                reference="1",
                title="Scope",
                signals=TaxonomySignalProfile(canonical_section="scope", heading="Scope"),
                plan=plan,
            ),
        ),
    )


def test_round_trips_versioned_routing_artifact(tmp_path: Path) -> None:
    repository = FileSystemSemanticRoutingArtifactRepository(tmp_path)
    artifact = _artifact()

    repository.save(artifact)

    path = repository.artifact_path("TEST", "contract", "1.0.0")
    assert path == tmp_path / "routing" / "TEST" / "contract" / "1.0.0" / "routing.json"
    assert repository.load("TEST", "contract", "1.0.0") == artifact


def test_rejects_path_components() -> None:
    repository = FileSystemSemanticRoutingArtifactRepository(Path(".atlas/data"))

    with pytest.raises(ValueError, match="must not contain path components"):
        repository.artifact_path("../TEST", "contract", "1.0.0")
