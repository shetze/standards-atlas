from pathlib import Path


def test_semantic_extraction_domain_and_ports_do_not_depend_on_graph_providers() -> None:
    roots = [
        Path("src/standards_atlas/domain/model/semantic_extraction.py"),
        Path("src/standards_atlas/application/ports/semantic_extraction.py"),
    ]
    forbidden = ("rdflib", "neo4j", "graphrag", "networkx", "sparql")
    for path in roots:
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source
