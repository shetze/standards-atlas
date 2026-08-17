"""Filesystem persistence for formula transcription enrichment artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from standards_atlas.application.model.formula_transcription import FormulaTranscriptionArtifact


class FileSystemFormulaTranscriptionRepository:
    """Store formula transcriptions separately from canonical documents."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._root = workspace / "enrichments" / "formula-transcriptions"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: FormulaTranscriptionArtifact) -> None:
        self._path(artifact.formula_id).write_text(
            json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load(self, formula_id: str) -> FormulaTranscriptionArtifact:
        path = self._path(formula_id)
        if not path.exists():
            raise FileNotFoundError(f"No formula transcription found for: {formula_id}")
        return FormulaTranscriptionArtifact.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, formula_id: str) -> bool:
        return self._path(formula_id).exists()

    def _path(self, formula_id: str) -> Path:
        digest = hashlib.sha256(formula_id.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"
