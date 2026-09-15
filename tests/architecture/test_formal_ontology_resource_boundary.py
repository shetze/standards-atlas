"""Architecture guards for the active clean-break formal ontology resources."""

from pathlib import Path

ROOT = Path("src/standards_atlas/resources/formal_ontologies")
NAMESPACE = "http://lunetix.org/standards-atlas#"


def test_only_current_formal_ontology_resources_are_packaged() -> None:
    expected = {
        ROOT / "standards-atlas-core" / "2.0.0" / "ontology.ttl",
        ROOT / "standards-atlas-core" / "2.0.0" / "ontology.yaml",
        ROOT / "functional-safety" / "2.1.0" / "ontology.ttl",
        ROOT / "functional-safety" / "2.1.0" / "ontology.yaml",
    }
    assert {path for path in ROOT.glob("*/*/*") if path.is_file()} == expected


def test_formal_ontologies_share_the_stable_stat_namespace() -> None:
    for path in ROOT.glob("*/*/ontology.ttl"):
        text = path.read_text(encoding="utf-8")
        assert f"@prefix stat: <{NAMESPACE}> ." in text


def test_formal_ontology_resources_do_not_embed_standard_instances() -> None:
    for path in ROOT.glob("*/*/ontology.ttl"):
        text = path.read_text(encoding="utf-8")
        for token in ("ISO26262", "IEC61508", "EN50716", "EN50128"):
            assert token not in text
