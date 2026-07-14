"""Persist review Markdown, override YAML and reviewed alignment privately."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml

from standards_atlas.application.model.alignment import AlignmentResult
from standards_atlas.application.model.alignment_review import AlignmentOverrideDocument


class AlignmentReviewRepository:
    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "alignments"

    def review_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "review.md")

    def generated_markdown_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "review.generated.md")

    def edited_markdown_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "review.edited.md")

    def overrides_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "overrides.yaml")

    def reviewed_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "reviewed.json")

    def save_review(self, document_key: str, markdown: str) -> Path:
        return self._atomic_write(self.review_path(document_key), markdown)

    def save_full_document_review(
        self,
        document_key: str,
        markdown: str,
        *,
        reset_edited: bool = False,
    ) -> tuple[Path, Path]:
        generated = self._atomic_write(self.generated_markdown_path(document_key), markdown)
        edited = self.edited_markdown_path(document_key)
        if reset_edited or not edited.exists():
            self._atomic_write(edited, markdown)
        return generated, edited

    def load_generated_markdown(self, document_key: str) -> str:
        return self.generated_markdown_path(document_key).read_text(encoding="utf-8")

    def load_edited_markdown(self, document_key: str) -> str:
        return self.edited_markdown_path(document_key).read_text(encoding="utf-8")

    def create_overrides(self, document_key: str, source_alignment_hash: str) -> Path:
        path = self.overrides_path(document_key)
        if path.exists():
            return path
        text = (
            "schema_version: 1\n"
            f"document_key: {document_key}\n"
            f"source_alignment_hash: {source_alignment_hash}\n"
            "overrides:\n"
        )
        return self._atomic_write(path, text)

    def save_overrides(
        self,
        document_key: str,
        overrides: AlignmentOverrideDocument,
    ) -> Path:
        payload = overrides.model_dump(mode="json")
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        return self._atomic_write(self.overrides_path(document_key), text)

    def load_overrides(self, document_key: str) -> AlignmentOverrideDocument:
        payload = yaml.safe_load(self.overrides_path(document_key).read_text(encoding="utf-8"))
        return AlignmentOverrideDocument.model_validate(payload)

    def save_reviewed(self, document_key: str, result: AlignmentResult) -> Path:
        return self._atomic_write(
            self.reviewed_path(document_key),
            result.model_dump_json(indent=2) + "\n",
        )

    def load_reviewed(self, document_key: str) -> AlignmentResult:
        return AlignmentResult.model_validate_json(
            self.reviewed_path(document_key).read_text(encoding="utf-8")
        )

    @staticmethod
    def hash_alignment(result: AlignmentResult) -> str:
        payload = result.model_dump_json(exclude={"metadata": {"created_at"}})
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _atomic_write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
        return path

    def _private_path(self, document_key: str, filename: str) -> Path:
        key = document_key.strip()
        if not key or key in {".", ".."} or Path(key).is_absolute() or "/" in key or "\\" in key:
            raise ValueError("Document key must not contain path components")
        path = (self._root / key / filename).resolve()
        if not path.is_relative_to(self._workspace):
            raise ValueError("Review artefacts must remain below the private workspace")
        return path
