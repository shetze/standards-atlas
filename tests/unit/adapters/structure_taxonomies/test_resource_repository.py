import pytest

from standards_atlas.adapters.structure_taxonomies import (
    ResourceStructuralTaxonomyDefinitionRepository,
)


def test_repository_loads_versioned_structure_taxonomy_resource() -> None:
    definition = ResourceStructuralTaxonomyDefinitionRepository().load(
        "document.iec-directives-2", "1.0.0"
    )

    assert definition.taxonomy_id == "document.iec-directives-2"
    assert definition.version == "1.0.0"
    assert "normative_technical_elements" in definition.categories


def test_repository_rejects_unknown_taxonomy() -> None:
    with pytest.raises(KeyError, match="not found"):
        ResourceStructuralTaxonomyDefinitionRepository().load("document.unknown", "1.0.0")
