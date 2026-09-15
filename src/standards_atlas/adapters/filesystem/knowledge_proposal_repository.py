"""File-system persistence for non-canonical document knowledge proposals."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.domain.model import DocumentKnowledgeProposal

CURRENT_DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION = 1


class FileSystemDocumentKnowledgeProposalRepository:
    """Persist proposals under a run-scoped workspace separate from canonical documents."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._root = workspace / "knowledge-proposals"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, proposal: DocumentKnowledgeProposal) -> None:
        payload = {
            "schema_version": CURRENT_DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
            "proposal": proposal.model_dump(mode="json"),
        }
        require_current_payload("document-knowledge-proposal", payload)
        require_current_payload("document-knowledge-proposal", payload["proposal"])
        path = self._path(proposal.proposal_run_id, proposal.source_document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load(
        self,
        proposal_run_id: str,
        document_key: str,
    ) -> DocumentKnowledgeProposal | None:
        path = self._path(proposal_run_id, document_key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        require_supported_schema("document-knowledge-proposal", payload.get("schema_version"))
        data = payload.get("proposal")
        if not isinstance(data, dict):
            raise ValueError("document knowledge proposal payload is missing proposal")
        require_supported_schema("document-knowledge-proposal", data.get("schema_version"))
        proposal = DocumentKnowledgeProposal.model_validate(data)
        if proposal.proposal_run_id != proposal_run_id:
            raise ValueError("document knowledge proposal run id does not match repository path")
        if proposal.source_document_key != document_key:
            raise ValueError(
                "document knowledge proposal document key does not match repository path"
            )
        return proposal

    def _path(self, proposal_run_id: str, document_key: str) -> Path:
        return (
            self._root
            / self._safe_component(proposal_run_id)
            / (f"{self._safe_component(document_key)}.json")
        )

    @staticmethod
    def _safe_component(value: str) -> str:
        safe = (
            value.strip().replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
        )
        if not safe or safe in {".", ".."}:
            raise ValueError(
                "knowledge proposal repository key must identify a safe path component"
            )
        return safe
