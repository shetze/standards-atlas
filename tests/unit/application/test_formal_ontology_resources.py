from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE, FORMAL_SEMANTIC_PREFIX


@pytest.fixture()
def repository() -> ResourceFormalOntologyRepository:
    return ResourceFormalOntologyRepository()


def test_core_ontology_uses_canonical_namespace(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("standards-atlas-core", "1.0.0")
    assert definition.namespace == FORMAL_SEMANTIC_NAMESPACE
    assert definition.prefix == FORMAL_SEMANTIC_PREFIX
    assert definition.imports == ()
    text = repository.read_text("standards-atlas-core", "1.0.0")
    assert "stat:Clause a owl:Class" in text
    assert "stat:ContextFrame a owl:Class" in text
    assert "stat:KnowledgeDomain a owl:Class" in text


def test_functional_safety_ontology_imports_core(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("functional-safety", "1.0.0")
    assert definition.imports == ("http://lunetix.org/standards-atlas/core/1.0.0",)
    text = repository.read_text("functional-safety", "1.0.0")
    assert "owl:imports <http://lunetix.org/standards-atlas/core/1.0.0>" in text
    assert "stat:VerificationActivity a owl:Class" in text
    assert "stat:SafetyIntegrityLevel a owl:Class" in text


def test_repository_rejects_missing_payload(tmp_path: Path) -> None:
    base = tmp_path / "broken" / "1.0.0"
    base.mkdir(parents=True)
    (base / "ontology.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: broken",
                "version: 1.0.0",
                "ontology_iri: http://example.invalid/broken",
                "version_iri: http://example.invalid/broken/1.0.0",
                f"namespace: {FORMAL_SEMANTIC_NAMESPACE}",
                f"prefix: {FORMAL_SEMANTIC_PREFIX}",
                "resource: ontology.ttl",
                "imports: []",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not exist"):
        ResourceFormalOntologyRepository(tmp_path).load("broken", "1.0.0")


def test_slice3_core_projection_vocabulary_is_versioned(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("standards-atlas-core", "1.1.0")
    assert definition.version_iri == "http://lunetix.org/standards-atlas/core/1.1.0"
    text = repository.read_text("standards-atlas-core", "1.1.0")
    assert "stat:ContextFacet a owl:Class" in text
    assert "stat:assertionSubject a owl:ObjectProperty" in text
    assert "stat:projectionRuleVersion a owl:DatatypeProperty" in text


def test_slice3_functional_safety_ontology_imports_core_1_1(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("functional-safety", "1.1.0")
    assert definition.imports == ("http://lunetix.org/standards-atlas/core/1.1.0",)
