from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE, FORMAL_SEMANTIC_PREFIX


@pytest.fixture()
def repository() -> ResourceFormalOntologyRepository:
    return ResourceFormalOntologyRepository()


def test_core_2_0_uses_canonical_namespace_and_engineering_artifact_model(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("standards-atlas-core", "2.0.0")
    assert definition.namespace == FORMAL_SEMANTIC_NAMESPACE
    assert definition.prefix == FORMAL_SEMANTIC_PREFIX
    assert definition.imports == ()
    assert definition.version_iri == "http://lunetix.org/standards-atlas/core/2.0.0"

    text = repository.read_text("standards-atlas-core", "2.0.0")
    for term in (
        "stat:EngineeringArtifact a owl:Class",
        "stat:WorkProduct a owl:Class ; rdfs:subClassOf stat:EngineeringArtifact",
        "stat:Specification a owl:Class ; rdfs:subClassOf stat:WorkProduct",
        "stat:Plan a owl:Class ; rdfs:subClassOf stat:WorkProduct",
        "stat:Report a owl:Class ; rdfs:subClassOf stat:WorkProduct",
        "stat:EngineeringRecord a owl:Class ; rdfs:subClassOf stat:WorkProduct",
        "stat:specifies a owl:ObjectProperty",
        "stat:plans a owl:ObjectProperty",
        "stat:records a owl:ObjectProperty",
        "stat:reportsOn a owl:ObjectProperty",
        "stat:producedBy a owl:ObjectProperty",
        "stat:usedBy a owl:ObjectProperty",
        "stat:tracesTo a owl:ObjectProperty",
        "stat:providesEvidenceFor a owl:ObjectProperty",
        "stat:responsibleFor a owl:ObjectProperty",
    ):
        assert term in text

    for removed in (
        "stat:Artifact a owl:Class",
        "stat:EvidenceArtifact",
        "stat:statementFunction",
        "stat:knowledgeKind",
        "stat:processFunction",
        "stat:roleSemanticsPresent",
        "stat:roleRelationClass",
    ):
        assert removed not in text


def test_functional_safety_2_0_imports_core_and_models_reports_as_work_products(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("functional-safety", "2.0.0")
    assert definition.imports == ("http://lunetix.org/standards-atlas/core/2.0.0",)
    text = repository.read_text("functional-safety", "2.0.0")
    assert "owl:imports <http://lunetix.org/standards-atlas/core/2.0.0>" in text
    for term in (
        "stat:VerificationPlan a owl:Class ; rdfs:subClassOf stat:Plan",
        "stat:VerificationReport a owl:Class ; rdfs:subClassOf stat:Report",
        "stat:ValidationReport a owl:Class ; rdfs:subClassOf stat:Report",
        "stat:AssessmentReport a owl:Class ; rdfs:subClassOf stat:Report",
        "stat:VerificationCriterion a owl:Class ; rdfs:subClassOf stat:Criterion",
        "stat:VerificationActivity a owl:Class",
        "stat:SafetyIntegrityLevel a owl:Class",
    ):
        assert term in text
    assert "EvidenceArtifact" not in text
    assert "SafetyEvidence" not in text


def test_core_2_0_declares_explicit_source_extraction_view(
    repository: ResourceFormalOntologyRepository,
) -> None:
    definition = repository.load("standards-atlas-core", "2.0.0")
    assert "EngineeringArtifact" in definition.extraction_vocabulary.classes
    assert "WorkProduct" in definition.extraction_vocabulary.classes
    assert "specifies" in definition.extraction_vocabulary.properties
    assert "providesEvidenceFor" in definition.extraction_vocabulary.properties
    assert "containsClause" not in definition.extraction_vocabulary.properties
    assert "confidence" not in definition.extraction_vocabulary.properties


def test_repository_rejects_missing_payload(tmp_path: Path) -> None:
    base = tmp_path / "broken" / "2.0.0"
    base.mkdir(parents=True)
    (base / "ontology.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: broken",
                "version: 2.0.0",
                "ontology_iri: http://example.invalid/broken",
                "version_iri: http://example.invalid/broken/2.0.0",
                f"namespace: {FORMAL_SEMANTIC_NAMESPACE}",
                f"prefix: {FORMAL_SEMANTIC_PREFIX}",
                "resource: ontology.ttl",
                "imports: []",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not exist"):
        ResourceFormalOntologyRepository(tmp_path).load("broken", "2.0.0")


def test_repository_rejects_undeclared_extraction_term(tmp_path: Path) -> None:
    base = tmp_path / "broken" / "2.0.0"
    base.mkdir(parents=True)
    (base / "ontology.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: broken",
                "version: 2.0.0",
                "ontology_iri: http://example.invalid/broken",
                "version_iri: http://example.invalid/broken/2.0.0",
                f"namespace: {FORMAL_SEMANTIC_NAMESPACE}",
                f"prefix: {FORMAL_SEMANTIC_PREFIX}",
                "resource: ontology.ttl",
                "imports: []",
                "extraction_vocabulary:",
                "  classes: [MissingClass]",
                "  properties: []",
            ]
        ),
        encoding="utf-8",
    )
    (base / "ontology.ttl").write_text(
        "@prefix stat: <http://lunetix.org/standards-atlas#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "stat:PresentClass a owl:Class .\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="undeclared terms"):
        ResourceFormalOntologyRepository(tmp_path).load("broken", "2.0.0")
