"""Semantic ontology definition boundary."""

from .definition import (
    OntologyDefinition,
    OntologyDefinitionRepository,
    OntologyReference,
)
from .resource_repository import ResourceOntologyDefinitionRepository
from .role_semantics import LlmRoleSemanticsClassifier, RoleSemanticsClassifier, RoleSemanticsResult

__all__ = [
    "OntologyDefinition",
    "OntologyDefinitionRepository",
    "OntologyReference",
    "ResourceOntologyDefinitionRepository",
    "LlmRoleSemanticsClassifier",
    "RoleSemanticsClassifier",
    "RoleSemanticsResult",
]
