from standards_atlas.adapters.filesystem import FileSystemSemanticExtractionRepository
from standards_atlas.domain.model import DocumentSemanticExtraction


def test_round_trip(tmp_path) -> None:
    repository = FileSystemSemanticExtractionRepository(tmp_path)
    extraction = DocumentSemanticExtraction(source_document_key="IEC61508")
    repository.save(extraction)
    assert repository.load("IEC61508") == extraction
