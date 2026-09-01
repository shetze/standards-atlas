import pytest

from standards_atlas.adapters.gemara import GEMARA_SPEC_VERSION
from standards_atlas.adapters.gemara.contract import (
    artifact_version,
    control_catalog_id,
    guidance_catalog_id,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
)


def _document(*, version: str | None = "2026-09", year: int | None = 2026) -> PublicationDocument:
    return PublicationDocument.from_engineering_document(
        EngineeringDocument(
            key=DocumentKey(value="SAMPLE-1"),
            title="Sample Standard - Part 1",
            document_type=DocumentType.STANDARD,
            version=version,
            year=year,
            clauses=(),
        )
    )


def test_gemara_contract_has_one_current_specification_version() -> None:
    assert GEMARA_SPEC_VERSION == "1.1.0"


def test_catalog_identifiers_are_stable_across_layers() -> None:
    assert guidance_catalog_id("SAMPLE-1") == "sample-1"
    assert control_catalog_id("SAMPLE-1") == "sample-1-controls"


def test_artifact_version_prefers_explicit_version_and_falls_back_to_year() -> None:
    assert artifact_version(_document()) == "2026-09"
    assert artifact_version(_document(version=None)) == "2026"


def test_artifact_version_does_not_invent_cross_layer_version() -> None:
    with pytest.raises(ValueError, match="needs a version or year"):
        artifact_version(_document(version=None, year=None))
