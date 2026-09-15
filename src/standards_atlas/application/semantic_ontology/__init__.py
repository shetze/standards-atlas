"""Semantic ontology definition boundary."""

from .definition import OntologyDefinition, OntologyDefinitionRepository, OntologyReference
from .resource_repository import ResourceOntologyDefinitionRepository

__all__ = [
    "OntologyDefinition",
    "OntologyDefinitionRepository",
    "OntologyReference",
    "ResourceOntologyDefinitionRepository",
]
