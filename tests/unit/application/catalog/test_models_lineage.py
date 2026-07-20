from pathlib import Path

import yaml

from standards_atlas.application.catalog.models import (
    NormativeState,
    RelationType,
    StandardCatalog,
)


def test_catalog_models_railway_software_lineage() -> None:
    catalog_path = Path(__file__).parents[4] / "catalogs" / "standards.yaml"
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    model = StandardCatalog.model_validate(payload)
    lineage = next(item for item in model.lineages if item.key == "cenelec-railway-software-safety")
    assert lineage.members == ("EN50128", "EN50657", "EN50716")

    en50128 = model.family("EN50128")
    en50657 = model.family("EN50657")
    en50716 = model.family("EN50716")

    assert en50128.status.normative_state == NormativeState.SUPERSEDED
    assert en50657.status.normative_state == NormativeState.SUPERSEDED
    assert en50716.status.normative_state == NormativeState.CURRENT
    assert any(
        relation.type == RelationType.ADAPTS and relation.target == "EN50128"
        for relation in en50657.relations
    )
    assert any(
        relation.type == RelationType.SPECIALIZES and relation.target == "EN50128"
        for relation in en50657.relations
    )
    assert any(
        relation.type == RelationType.SUPERSEDES and relation.target == "EN50128"
        for relation in en50716.relations
    )
    assert any(
        relation.type == RelationType.CONSOLIDATES and relation.target == "EN50657"
        for relation in en50716.relations
    )
