"""Formula transcription enrichment and deterministic document application."""

from __future__ import annotations

from typing import Any

from standards_atlas.application.model.formula_transcription import (
    FormulaTranscriptionArtifact,
    FormulaTranscriptionProvenance,
)
from standards_atlas.application.ports.formula_transcriptions import (
    FormulaTranscriptionDocumentRepository,
    FormulaTranscriptionRepository,
)
from standards_atlas.domain.model import DocumentKey, FormulaBlock


class FormulaTranscriptionService:
    """Expose visual formulas and apply reviewed transcription artifacts."""

    def __init__(
        self,
        documents: FormulaTranscriptionDocumentRepository,
        transcriptions: FormulaTranscriptionRepository,
    ) -> None:
        self._documents = documents
        self._transcriptions = transcriptions

    def list_untranscribed(
        self, *, document_keys: list[str] | None = None, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        allowed = set(document_keys or ())
        results: list[dict[str, Any]] = []
        for document in self._documents.list():
            if allowed and document.key.value not in allowed:
                continue
            for clause in document.clauses:
                for index, block in enumerate(clause.content):
                    if (
                        not isinstance(block, FormulaBlock)
                        or block.extraction_status != "visual_only"
                    ):
                        continue
                    formula_id = _formula_id(document.key.value, clause.id.value, block.id)
                    if self._transcriptions.exists(formula_id):
                        continue
                    results.append(
                        self._descriptor(
                            document.key.value, clause.id.value, index, formula_id, block
                        )
                    )
        return results[offset : offset + limit]

    def get(self, formula_id: str) -> dict[str, Any]:
        document, clause, index, block = self._locate(formula_id)
        payload = self._descriptor(document.key.value, clause.id.value, index, formula_id, block)
        payload["context"] = _context(clause.content, index)
        return payload

    def submit(
        self,
        formula_id: str,
        *,
        latex: str,
        actor: str,
        provider: str | None = None,
        model: str | None = None,
        confidence: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        expression = latex.strip()
        if not expression:
            raise ValueError("latex transcription must not be empty")
        document, clause, index, block = self._locate(formula_id)
        artifact = FormulaTranscriptionArtifact(
            formula_id=formula_id,
            document_key=document.key.value,
            clause_id=clause.id.value,
            block_id=block.id,
            source_content_hash=block.content_hash,
            expression=expression,
            confidence=confidence,
            provenance=FormulaTranscriptionProvenance(
                actor=actor, provider=provider, model=model, notes=notes
            ),
        )
        self._transcriptions.save(artifact)

        enriched_block = block.model_copy(
            update={
                "expression": expression,
                "representation": "latex",
                "extraction_status": "machine_transcribed",
            }
        )
        content = list(clause.content)
        content[index] = enriched_block
        enriched_clause = clause.with_baseline_updates(content=tuple(content))
        clauses = list(document.clauses)
        clause_index = next(i for i, item in enumerate(clauses) if item.id == clause.id)
        clauses[clause_index] = enriched_clause
        self._documents.save(document.model_copy(update={"clauses": tuple(clauses)}))
        return artifact.model_dump(mode="json")

    def _locate(self, formula_id: str):
        parts = formula_id.split("::", 2)
        if len(parts) != 3:
            raise ValueError("invalid formula_id")
        document_key, clause_id, block_id = parts
        document = self._documents.load(DocumentKey(value=document_key))
        for clause in document.clauses:
            if clause.id.value != clause_id:
                continue
            for index, block in enumerate(clause.content):
                if isinstance(block, FormulaBlock) and block.id == block_id:
                    return document, clause, index, block
        raise KeyError(f"Formula not found: {formula_id}")

    @staticmethod
    def _descriptor(
        document_key: str, clause_id: str, index: int, formula_id: str, block: FormulaBlock
    ):
        return {
            "formula_id": formula_id,
            "document_key": document_key,
            "clause_id": clause_id,
            "block_id": block.id,
            "content_index": index,
            "extraction_status": block.extraction_status,
            "image": {
                "media_type": block.media_type,
                "content_hash": block.content_hash,
                "data_uri": block.embedded_data_uri,
            },
            "source_evidence": [item.model_dump(mode="json") for item in block.source_evidence],
        }


def _formula_id(document_key: str, clause_id: str, block_id: str) -> str:
    return f"{document_key}::{clause_id}::{block_id}"


def _context(content: tuple[Any, ...], index: int) -> dict[str, str | None]:
    def rendered(position: int) -> str | None:
        if position < 0 or position >= len(content):
            return None
        item = content[position]
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None

    return {"preceding_text": rendered(index - 1), "following_text": rendered(index + 1)}
