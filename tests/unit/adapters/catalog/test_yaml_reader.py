from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader


def test_reads_project_catalog() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    assert len(catalog.families) == 17
    assert (
        sum(
            1
            if family.source
            else len(family.parts) + sum(len(part.supplements) for part in family.parts)
            for family in catalog.families
        )
        == 38
    )
    assert catalog.family("ISO26262").classification.industry_sectors == ("automotive",)
    assert catalog.profile("railway-functional-safety").families[-1] == "IEC61508"


def test_iec61508_3_1_is_a_supplement_of_part_3() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    family = catalog.family("IEC61508")
    part = next(item for item in family.parts if item.key == "IEC61508-3")

    assert len(part.supplements) == 1
    supplement = part.supplements[0]
    assert supplement.key == "IEC61508-3-1"
    assert supplement.supplement == "1"
    assert supplement.document_type.value == "technical-specification"
    assert supplement.relations[0].type.value == "supplements"
    assert supplement.relations[0].target == "IEC61508-3"
    assert all(item.key != "IEC61508-3-1" for item in family.parts)
