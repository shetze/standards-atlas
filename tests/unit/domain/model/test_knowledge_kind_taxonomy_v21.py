from pathlib import Path

import yaml

from standards_atlas.domain.model import KnowledgeKind


def test_current_taxonomy_uses_one_combined_technique_measure_kind() -> None:
    taxonomy_path = Path(
        "src/standards_atlas/resources/semantic/tasks/"
        "statement-function-classification/2.1.0/taxonomy.yaml"
    )
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))

    assert "technique_or_measure" in taxonomy["knowledge_kinds"]
    assert "technique" not in taxonomy["knowledge_kinds"]
    assert "method_or_measure" not in taxonomy["knowledge_kinds"]
    assert KnowledgeKind.TECHNIQUE_OR_MEASURE.value == "technique_or_measure"
