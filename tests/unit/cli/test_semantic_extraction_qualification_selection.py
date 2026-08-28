from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.cli.commands.evaluation_commands.semantic_extraction_qualification import (
    _selected_clause_ids_by_document,
)


def test_selected_clause_ids_resolve_current_nested_context() -> None:
    examples = (
        EvaluationExample(
            id="clause-a",
            input={
                "content": {"text": "example"},
                "context": {
                    "document_key": "ISO26262-11",
                    "clause_id": "clause-a",
                },
            },
            expected={},
        ),
        EvaluationExample(
            id="clause-b",
            input={
                "context": {
                    "document_key": "IEC61508-3-1",
                    "clause_id": "clause-b",
                }
            },
            expected={},
        ),
    )

    assert _selected_clause_ids_by_document(examples) == {
        "IEC61508-3-1": {"clause-b"},
        "ISO26262-11": {"clause-a"},
    }


def test_qualification_eligibility_context_uses_latest_cascade_stage(tmp_path) -> None:
    import json

    from standards_atlas.cli.commands.evaluation_commands.semantic_extraction_qualification import (
        _load_qualification_eligibility_contexts,
    )
    from standards_atlas.domain.model import ApplicabilityFunction, KnowledgeKind

    (tmp_path / "cascade" / "efficient-local").mkdir(parents=True)
    (tmp_path / "cascade" / "escalation").mkdir(parents=True)
    (tmp_path / "cascade-provenance.json").write_text(
        json.dumps(
            {
                "stages": [
                    {"stage_id": "efficient-local"},
                    {"stage_id": "escalation"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "cascade" / "efficient-local" / "consensus-report.json").write_text(
        json.dumps(
            {
                "clauses": [
                    {
                        "document_key": "DOC",
                        "clause_id": "c1",
                        "proposed_knowledge_kinds": ["artifact"],
                        "applicability_present": False,
                        "role_semantics_present": False,
                    },
                    {
                        "document_key": "DOC",
                        "clause_id": "c2",
                        "primary_knowledge_kind": "process",
                        "applicability_present": False,
                        "role_semantics_present": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "cascade" / "escalation" / "consensus-report.json").write_text(
        json.dumps(
            {
                "clauses": [
                    {
                        "document_key": "DOC",
                        "clause_id": "c1",
                        "proposed_knowledge_kinds": ["technique_or_measure"],
                        "applicability_present": True,
                        "proposed_applicability_functions": ["inclusion"],
                        "role_semantics_present": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    contexts = _load_qualification_eligibility_contexts(tmp_path)

    assert contexts[("DOC", "c1")].knowledge_kinds == (KnowledgeKind.TECHNIQUE_OR_MEASURE,)
    assert contexts[("DOC", "c1")].applicability_present is True
    assert contexts[("DOC", "c1")].applicability_functions == (ApplicabilityFunction.INCLUSION,)
    assert contexts[("DOC", "c1")].role_semantics_present is True
    assert contexts[("DOC", "c2")].knowledge_kinds == (KnowledgeKind.PROCESS,)


def test_extraction_model_resolves_through_manifest_model_catalog() -> None:
    from pathlib import Path

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        QualificationMatrixManifest,
    )
    from standards_atlas.cli.commands.evaluation_commands.semantic_extraction_qualification import (
        _resolve_extraction_model,
    )

    manifest = QualificationMatrixManifest.load(
        Path("manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml")
    )
    candidate = _resolve_extraction_model(
        manifest, manifest.semantic_extraction_qualification.model
    )

    assert candidate is not None
    assert candidate.provider == "ramalama"
    assert candidate.id == "mistral-small-3.2-24b-instruct-q4-k-m"
    assert candidate.model_ref is not None
    assert candidate.model_ref.startswith("hf.co://")
