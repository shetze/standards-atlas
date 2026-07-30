import json

from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.application.model import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedList,
    ExtractedListItem,
    ExtractionMetadata,
)
from standards_atlas.application.normalization import DocumentNormalizer


def test_repository_writes_separate_method_technique_index(tmp_path) -> None:
    source = ExtractedDocument(
        source_id="sample",
        items=(
            ExtractedHeading(
                id="heading",
                sequence_number=0,
                text="Methods and techniques",
                observed_level=2,
            ),
            ExtractedList(
                id="list",
                sequence_number=1,
                items=(ExtractedListItem(text="Fault tree analysis"),),
            ),
        ),
        metadata=ExtractionMetadata(converter="docling"),
    )
    normalized = DocumentNormalizer().normalize(source)
    repository = NormalizationArtifactRepository(tmp_path)

    repository.save("ISO26262-11", normalized)

    payload = json.loads(
        repository.method_technique_index_path("ISO26262-11").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert payload["document_key"] == "ISO26262-11"
    assert payload["candidates"][0]["name"] == "Fault tree analysis"
