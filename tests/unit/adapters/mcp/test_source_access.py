from pathlib import Path

import pytest

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.service import McpClauseService
from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor
from standards_atlas.domain.model import ClauseType


class _Provider:
    def __init__(self, document_key: str = "DOC") -> None:
        self.clause = ClauseDescriptor(
            id="child",
            document_key=document_key,
            reference=f"{document_key}:1.1",
            clause_reference="1.1",
            content_hash="sha256:" + ("a" * 64),
            clause_type=ClauseType.CLAUSE,
            heading="Protected child heading",
            text="Protected child body",
            ancestor_headings=(
                {"clause_id": "parent", "reference": "1", "heading": "Protected parent heading"},
            ),
        )

    def get_clause(self, clause_id: str):
        if clause_id != self.clause.id:
            raise KeyError(clause_id)
        return self.clause


class _FormulaService:
    def get(self, formula_id: str):
        return {
            "formula_id": formula_id,
            "document_key": "DOC",
            "clause_id": "child",
            "block_id": "f1",
            "context": {
                "preceding_text": "Protected before",
                "following_text": "Protected after",
            },
            "source_evidence": [],
        }


def _config(tmp_path: Path, *, allowed=("DOC",), clause_text=False) -> McpServerConfig:
    return McpServerConfig.model_validate(
        {
            "workspace": str(tmp_path),
            "allowed_document_keys": list(allowed),
            "expose": {"clause_text": clause_text, "source_paths": False},
        }
    )


def test_clause_text_policy_also_redacts_heading_and_ancestor_context(tmp_path: Path) -> None:
    service = McpClauseService(_Provider(), _config(tmp_path))

    payload = service.get_clause("child")

    assert payload["text"] == ""
    assert payload["heading"] is None
    assert payload["ancestor_headings"] == []
    dumped = str(payload)
    assert "Protected child" not in dumped
    assert "Protected parent" not in dumped


def test_formula_context_obeys_same_text_release_boundary(tmp_path: Path) -> None:
    service = McpClauseService(_Provider(), _config(tmp_path))
    service._formula_transcriptions = _FormulaService()

    payload = service.get_formula("DOC::child::f1")

    assert payload["context"] == {"preceding_text": None, "following_text": None}
    assert "Protected" not in str(payload)


def test_knowledge_table_serializer_does_not_expose_cells_when_text_is_disabled(
    tmp_path: Path,
) -> None:
    service = McpClauseService(_Provider(), _config(tmp_path))
    payload = {
        "title": "Protected table title",
        "header_rows": [["Protected header"]],
        "records": [
            {
                "cells": [{"text": "Protected cell"}],
                "technique_recommendation": {"text": "Protected interpretation"},
                "structured_knowledge": {"label": "Protected structure"},
            }
        ],
    }

    redacted = service._serialize_knowledge_table(payload)

    assert redacted["title"] is None
    assert redacted["header_rows"] == []
    assert redacted["records"][0]["cells"][0]["text"] == ""
    assert redacted["records"][0]["technique_recommendation"] is None
    assert redacted["records"][0]["structured_knowledge"] is None
    assert "Protected" not in str(redacted)


def test_document_allowlist_still_blocks_source_access(tmp_path: Path) -> None:
    service = McpClauseService(_Provider(document_key="OTHER"), _config(tmp_path))

    with pytest.raises(KeyError, match="not exposed"):
        service.get_clause("child")
