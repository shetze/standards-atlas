"""Load structural-taxonomy contracts from packaged YAML resources."""

from __future__ import annotations

from importlib.resources import files

import yaml

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.structure.taxonomy_definition import (
    StructuralTaxonomyDefinition,
)


class ResourceStructuralTaxonomyDefinitionRepository:
    """Resolve document/domain taxonomy definitions shipped with the package."""

    def load(self, taxonomy_id: str, version: str) -> StructuralTaxonomyDefinition:
        namespace, separator, name = taxonomy_id.partition(".")
        if not separator or namespace not in {"document", "domain"} or not name:
            raise KeyError(f"unsupported structural taxonomy id: {taxonomy_id}")
        resource = (
            files("standards_atlas.resources")
            / "structure-taxonomies"
            / namespace
            / name
            / version
            / "taxonomy.yaml"
        )
        if not resource.is_file():
            raise KeyError(f"structural taxonomy definition not found: {taxonomy_id}@{version}")
        payload = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
        require_supported_schema("structural-taxonomy-resource", payload.get("schema_version"))
        loaded_id = str(payload.get("id", ""))
        loaded_version = str(payload.get("version", ""))
        if loaded_id != taxonomy_id or loaded_version != version:
            raise ValueError(
                "structural taxonomy resource identity mismatch: "
                f"expected {taxonomy_id}@{version}, got {loaded_id}@{loaded_version}"
            )
        categories = frozenset(str(item) for item in payload.get("categories", ()))
        if not categories:
            raise ValueError(f"structural taxonomy has no categories: {taxonomy_id}@{version}")
        return StructuralTaxonomyDefinition(
            schema_version=1,
            taxonomy_id=taxonomy_id,
            version=version,
            categories=categories,
        )
