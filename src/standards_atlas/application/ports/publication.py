"""Ports for runtime publication projections."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.application.model import PublicationDocument


class PublicationDocumentProvider(Protocol):
    """Resolve physical or composed publication documents without persistence."""

    def load(
        self,
        document_key: str,
        *,
        part_keys: tuple[str, ...] = (),
        family_title: str | None = None,
    ) -> PublicationDocument: ...

    def list(self) -> tuple[PublicationDocument, ...]: ...
