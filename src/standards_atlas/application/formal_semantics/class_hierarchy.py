"""Deterministic class-hierarchy queries over packaged formal ontologies."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from .resource_repository import ResourceFormalOntologyRepository

_SUBCLASS = re.compile(
    r"stat:(?P<child>[A-Za-z][A-Za-z0-9_-]*)\s+a\s+owl:Class\s*;\s*"
    r"rdfs:subClassOf\s+stat:(?P<parent>[A-Za-z][A-Za-z0-9_-]*)"
)


class FormalClassHierarchy:
    """Transitive subclass queries without ontology inference beyond rdfs:subClassOf."""

    def __init__(self, parents: dict[str, frozenset[str]]) -> None:
        self._parents = dict(parents)

    def is_ancestor_or_same(self, ancestor: str, descendant: str) -> bool:
        if ancestor == descendant:
            return True
        seen: set[str] = set()
        pending = list(self._parents.get(descendant, ()))
        while pending:
            current = pending.pop()
            if current == ancestor:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self._parents.get(current, ()))
        return False

    def compatible(self, left: str, right: str) -> bool:
        return self.is_ancestor_or_same(left, right) or self.is_ancestor_or_same(right, left)

    def most_specific(self, classes: Iterable[str]) -> str:
        unique = set(classes)
        candidates = {
            candidate
            for candidate in unique
            if all(self.is_ancestor_or_same(other, candidate) for other in unique)
        }
        if len(candidates) != 1:
            raise ValueError(
                "compatible ontology class chain must have exactly one most-specific class"
            )
        return next(iter(candidates))


def load_formal_class_hierarchy(
    ontology_versions: tuple[str, ...],
    repository: ResourceFormalOntologyRepository | None = None,
) -> FormalClassHierarchy:
    """Load only declared subclass edges from the explicitly bound ontology resources."""
    if not ontology_versions:
        raise ValueError("formal class hierarchy requires explicit ontology versions")
    ontology_repository = repository or ResourceFormalOntologyRepository()
    parents: dict[str, set[str]] = defaultdict(set)
    for reference in ontology_versions:
        if reference.count("@") != 1:
            raise ValueError("ontology versions must use '<id>@<version>' references")
        ontology_id, version = reference.rsplit("@", 1)
        definition = ontology_repository.load(ontology_id, version)
        text = ontology_repository.read_text(ontology_id, version)
        for match in _SUBCLASS.finditer(text):
            child = f"{definition.namespace}{match.group('child')}"
            parent = f"{definition.namespace}{match.group('parent')}"
            parents[child].add(parent)
    return FormalClassHierarchy({key: frozenset(value) for key, value in parents.items()})
