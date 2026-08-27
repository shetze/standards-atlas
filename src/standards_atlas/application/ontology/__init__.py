"""Semantic ontology definition boundary."""

from .definition import (
    OntologyDefinition,
    OntologyDefinitionRepository,
    OntologyReference,
)
from .resource_repository import ResourceOntologyDefinitionRepository

__all__ = [
    "LlmRoleSemanticsClassifier",
    "OntologyDefinition",
    "OntologyDefinitionRepository",
    "OntologyReference",
    "ResourceOntologyDefinitionRepository",
    "RoleSemanticsClassifier",
    "RoleSemanticsResult",
]


def __getattr__(name: str):
    if name in {"LlmRoleSemanticsClassifier", "RoleSemanticsClassifier", "RoleSemanticsResult"}:
        from .role_semantics import (
            LlmRoleSemanticsClassifier,
            RoleSemanticsClassifier,
            RoleSemanticsResult,
        )

        return {
            "LlmRoleSemanticsClassifier": LlmRoleSemanticsClassifier,
            "RoleSemanticsClassifier": RoleSemanticsClassifier,
            "RoleSemanticsResult": RoleSemanticsResult,
        }[name]
    raise AttributeError(name)
