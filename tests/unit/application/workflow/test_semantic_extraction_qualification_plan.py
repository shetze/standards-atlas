from pathlib import Path

from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)


def test_v5_manifest_enables_semantic_extraction_qualification() -> None:
    manifest = QualificationMatrixManifest.load(
        Path("manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml")
    )
    assert manifest.semantic_extraction_qualification.enabled is True
    assert (
        "standards-atlas-core@1.1.0" in manifest.semantic_extraction_qualification.ontology_versions
    )
