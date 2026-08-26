"""Ports for rebuildable publication views."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from standards_atlas.application.model import ComposedDocumentView
from standards_atlas.domain.model import DocumentKey, EngineeringDocument


class ComposedDocumentViewStore(Protocol):
    def save(self, view: ComposedDocumentView) -> Path: ...
    def load(self, family_key: str) -> ComposedDocumentView: ...
    def exists(self, family_key: str) -> bool: ...


class PublicationDocumentReader(Protocol):
    def load(self, key: DocumentKey) -> EngineeringDocument: ...
    def list(self) -> tuple[EngineeringDocument, ...]: ...
