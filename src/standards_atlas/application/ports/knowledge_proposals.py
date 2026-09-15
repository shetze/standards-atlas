"""Ports for rebuildable assertion-centred knowledge proposals."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import DocumentKnowledgeProposal


class DocumentKnowledgeProposalRepository(Protocol):
    """Persistence boundary for non-canonical document knowledge proposals."""

    def save(self, proposal: DocumentKnowledgeProposal) -> None: ...

    def load(self, proposal_run_id: str, document_key: str) -> DocumentKnowledgeProposal | None: ...
