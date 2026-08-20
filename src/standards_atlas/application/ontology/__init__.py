"""Semantic ontology application boundary."""

from .definition import (
    OntologyDefinition,
    OntologyDefinitionRepository,
    OntologyProfile,
    OntologyReference,
)
from .engine import (
    OntologyClassifier,
    OntologyContext,
    OntologyDimensionResult,
    OntologyEngine,
    OntologyRegistry,
)
from .resource_repository import ResourceOntologyDefinitionRepository

__all__ = [
    "OntologyClassifier",
    "OntologyContext",
    "OntologyDefinition",
    "OntologyDefinitionRepository",
    "OntologyDimensionResult",
    "OntologyEngine",
    "OntologyProfile",
    "OntologyReference",
    "OntologyRegistry",
    "ResourceOntologyDefinitionRepository",
]
