"""Orchestrate Markdown review and manual alignment overrides."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.model.alignment import AlignmentResult
from standards_atlas.application.model.alignment_review import OverrideValidationResult
from standards_atlas.application.model.markdown_review import MarkdownReviewDiff
from standards_atlas.application.review import (
    AlignmentOverrideEngine,
    AlignmentReviewRenderer,
    FullDocumentReviewDiffer,
    FullDocumentReviewParser,
    FullDocumentReviewRenderer,
    MarkdownReviewOverrideBuilder,
)
from standards_atlas.domain.model import DocumentKey


class AlignmentReviewService:
    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalized = NormalizationArtifactRepository(workspace)
        self._candidates = ReferenceCandidateRepository(workspace)
        self._automatic = AlignmentArtifactRepository(workspace)
        self._review = AlignmentReviewRepository(workspace)
        self._engine = AlignmentOverrideEngine()
        self._renderer = AlignmentReviewRenderer()
        self._full_renderer = FullDocumentReviewRenderer()
        self._full_parser = FullDocumentReviewParser()
        self._full_differ = FullDocumentReviewDiffer()
        self._override_builder = MarkdownReviewOverrideBuilder()

    def generate_review(
        self,
        document_key: str,
        *,
        context_before: int = 2,
        context_after: int = 4,
    ) -> tuple[Path, Path]:
        automatic = self._automatic.load(document_key)
        normalized = self._normalized.load(document_key)
        candidates = self._candidates.load(document_key)
        engineering = self._documents.load(DocumentKey(value=document_key))
        markdown = self._renderer.render(
            automatic,
            normalized,
            candidates,
            engineering,
            context_before=context_before,
            context_after=context_after,
        )
        review_path = self._review.save_review(document_key, markdown)
        overrides_path = self._review.create_overrides(
            document_key,
            self._review.hash_alignment(automatic),
        )
        return review_path, overrides_path

    def export_full_document_review(
        self,
        document_key: str,
        *,
        reset_edited: bool = False,
    ) -> tuple[Path, Path]:
        markdown = self._full_renderer.render(
            self._normalized.load(document_key),
            self._automatic.load(document_key),
        )
        return self._review.save_full_document_review(
            document_key,
            markdown,
            reset_edited=reset_edited,
        )

    def diff_full_document_review(self, document_key: str) -> MarkdownReviewDiff:
        generated = self._full_parser.parse(self._review.load_generated_markdown(document_key))
        edited = self._full_parser.parse(self._review.load_edited_markdown(document_key))
        return self._full_differ.diff(generated, edited)

    def import_full_document_review(self, document_key: str) -> Path:
        diff = self.diff_full_document_review(document_key)
        if diff.content_changes:
            details = "; ".join(
                f"{change.item_id}: {change.message}" for change in diff.content_changes
            )
            raise ValueError(f"Reviewed Markdown changes protected content: {details}")
        automatic = self._automatic.load(document_key)
        engineering = self._documents.load(DocumentKey(value=document_key))
        overrides = self._override_builder.build(diff, engineering, automatic)
        overrides = overrides.model_copy(
            update={"source_alignment_hash": self._review.hash_alignment(automatic)}
        )
        return self._review.save_overrides(document_key, overrides)

    def validate_full_document_review(self, document_key: str) -> MarkdownReviewDiff:
        diff = self.diff_full_document_review(document_key)
        if diff.content_changes:
            details = "; ".join(
                f"{change.item_id}: {change.message}" for change in diff.content_changes
            )
            raise ValueError(f"Reviewed Markdown changes protected content: {details}")
        return diff

    def validate_overrides(self, document_key: str) -> OverrideValidationResult:
        return self._engine.validate(
            self._review.load_overrides(document_key),
            self._automatic.load(document_key),
            self._normalized.load(document_key),
            self._candidates.load(document_key),
            self._documents.load(DocumentKey(value=document_key)),
        )

    def apply_overrides(self, document_key: str) -> AlignmentResult:
        automatic = self._automatic.load(document_key)
        overrides = self._review.load_overrides(document_key)
        expected_hash = self._review.hash_alignment(automatic)
        if overrides.source_alignment_hash not in {None, expected_hash}:
            raise ValueError(
                "Alignment overrides are stale because the automatic alignment changed."
            )
        result = self._engine.apply(
            overrides,
            automatic,
            self._normalized.load(document_key),
            self._candidates.load(document_key),
            self._documents.load(DocumentKey(value=document_key)),
        )
        self._review.save_reviewed(document_key, result)
        return result

    def load_reviewed(self, document_key: str) -> AlignmentResult:
        return self._review.load_reviewed(document_key)

    def reviewed_path(self, document_key: str) -> Path:
        return self._review.reviewed_path(document_key)
