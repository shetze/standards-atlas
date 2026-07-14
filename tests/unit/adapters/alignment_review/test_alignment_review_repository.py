from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
from standards_atlas.application.model import AlignmentOverrideDocument, IgnoreCandidateOverride


def test_override_yaml_roundtrip(tmp_path):
    repository = AlignmentReviewRepository(tmp_path / ".atlas")
    document = AlignmentOverrideDocument(
        document_key="DOC",
        overrides=(IgnoreCandidateOverride(candidate_item_id="i20"),),
    )
    path = repository.save_overrides("DOC", document)
    assert path.name == "overrides.yaml"
    assert repository.load_overrides("DOC") == document


def test_review_paths_remain_private(tmp_path):
    repository = AlignmentReviewRepository(tmp_path / ".atlas")
    assert repository.review_path("DOC").is_relative_to((tmp_path / ".atlas").resolve())


def test_create_overrides_writes_editable_empty_mapping(tmp_path):
    repository = AlignmentReviewRepository(tmp_path / ".atlas")

    path = repository.create_overrides("DOC", "alignment-hash")
    text = path.read_text(encoding="utf-8")

    assert "source_alignment_hash: alignment-hash" in text
    assert text.endswith("overrides:\n")
    assert "overrides: []" not in text

    loaded = repository.load_overrides("DOC")
    assert loaded.overrides == ()


def test_full_document_review_preserves_existing_edited_file(tmp_path):
    repository = AlignmentReviewRepository(tmp_path / ".atlas")
    generated, edited = repository.save_full_document_review("DOC", "first\n")
    edited.write_text("human edit\n", encoding="utf-8")

    repository.save_full_document_review("DOC", "second\n")

    assert generated.read_text(encoding="utf-8") == "second\n"
    assert edited.read_text(encoding="utf-8") == "human edit\n"


def test_full_document_review_can_reset_edited_file(tmp_path):
    repository = AlignmentReviewRepository(tmp_path / ".atlas")
    _, edited = repository.save_full_document_review("DOC", "first\n")
    edited.write_text("human edit\n", encoding="utf-8")

    repository.save_full_document_review("DOC", "second\n", reset_edited=True)

    assert edited.read_text(encoding="utf-8") == "second\n"
