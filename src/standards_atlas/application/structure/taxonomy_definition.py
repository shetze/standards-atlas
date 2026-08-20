"""Contracts for versioned structural-taxonomy definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StructuralTaxonomyDefinition:
    """Versioned category contract loaded independently from its algorithm."""

    taxonomy_id: str
    version: str
    categories: frozenset[str]
    schema_version: int = 1


class StructuralTaxonomyDefinitionRepository(Protocol):
    """Port for resolving a versioned structural-taxonomy contract."""

    def load(self, taxonomy_id: str, version: str) -> StructuralTaxonomyDefinition: ...
