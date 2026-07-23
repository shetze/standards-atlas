import json

from standards_atlas.adapters.artifact_lineage import (
    write_directory_lineage_manifest,
    write_file_lineage_manifest,
)
from standards_atlas.domain.model import (
    ArtifactLineage,
    Standard,
    StandardKey,
    artifact_reference,
)


def _document_with_lineage():
    document = Standard.from_name(
        key=StandardKey(value="SAMPLE"),
        name="Sample",
        year=2026,
    )
    artifact = artifact_reference("engineering_document", document)
    return document.model_copy(update={"lineage": ArtifactLineage(artifact=artifact)})


def test_artifact_identity_ignores_lineage_metadata() -> None:
    document = Standard.from_name(
        key=StandardKey(value="SAMPLE"),
        name="Sample",
        year=2026,
    )
    first = artifact_reference("engineering_document", document)
    with_lineage = document.model_copy(update={"lineage": ArtifactLineage(artifact=first)})

    second = artifact_reference("engineering_document", with_lineage)

    assert second == first


def test_file_export_manifest_references_engineering_parent(tmp_path) -> None:
    document = _document_with_lineage()
    target = tmp_path / "sample.md"
    target.write_text("# Sample\n", encoding="utf-8")

    manifest = write_file_lineage_manifest(
        target,
        document,
        kind="markdown_export",
        media_type="text/markdown",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert payload["artifact"]["kind"] == "markdown_export"
    assert payload["derived_from"] == [document.lineage.artifact.model_dump(mode="json")]


def test_directory_manifest_hashes_sorted_export_files(tmp_path) -> None:
    document = _document_with_lineage()
    target = tmp_path / "doorstop"
    target.mkdir()
    (target / "b.yml").write_text("b\n", encoding="utf-8")
    (target / "a.yml").write_text("a\n", encoding="utf-8")

    first = write_directory_lineage_manifest(
        target,
        document,
        kind="doorstop_export",
    )
    first_payload = first.read_text(encoding="utf-8")
    second = write_directory_lineage_manifest(
        target,
        document,
        kind="doorstop_export",
    )

    assert second.read_text(encoding="utf-8") == first_payload
