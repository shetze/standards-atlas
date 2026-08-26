"""Ports for disposable retrieval projections and tokenizer-specific indexing."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import RetrievalDocument, RetrievalProjection


class RetrievalProjectionWriter(Protocol):
    """Persist or forward a deterministic retrieval projection."""

    def write(self, projection: RetrievalProjection) -> None: ...


class RetrievalTokenizer(Protocol):
    """Tokenize one retrieval document according to its declared profile."""

    def tokenize(self, document: RetrievalDocument) -> tuple[int, ...]: ...
