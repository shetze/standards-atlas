from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    SamplingStrategy,
)
from standards_atlas.application.semantic_qualification.workflow import (
    BenchmarkManifest,
    CorpusBuildConfig,
)
from standards_atlas.application.services.evaluation import (
    EvaluationCorpusBuilder,
    EvaluationMatrixRunner,
    EvaluationReporter,
    EvaluationRunner,
)
from standards_atlas.domain.model import ClauseType


class FakeProvider:
    def list_clauses(self, **kwargs):
        return self.sample_clauses(**kwargs)

    def sample_clauses(self, **kwargs):
        return (
            ClauseDescriptor(
                id="DOC:1",
                document_key="DOC",
                reference="DOC:1",
                clause_reference="1",
                content_hash="sha256:" + "a" * 64,
                clause_type=ClauseType.REQUIREMENT,
                text="The supplier shall review the plan.",
            ),
        )


class FakeGateway:
    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={"summary": "Review the plan.", "confidence": 1.0},
            model=request.model or "default",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=5,
        )


def _write_resources(root: Path) -> None:
    prompt = root / "prompts" / "clause-summary" / "1.0.0"
    prompt.mkdir(parents=True)
    (prompt / "prompt.json").write_text('{"description":"test"}')
    (prompt / "system.txt").write_text("Summarize.")
    (prompt / "user.txt").write_text("{reference}: {text}")
    (prompt / "schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["summary", "confidence"],
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            }
        )
    )
    corpus = root / "corpora" / "clause-summary" / "1.0.0"
    corpus.mkdir(parents=True)
    (corpus / "dataset.json").write_text(
        json.dumps(
            {
                "examples": [
                    {
                        "id": "case-1",
                        "input": {"reference": "1", "text": "Review the plan."},
                        "expected": {"summary": "Review the plan.", "confidence": 1.0},
                    }
                ]
            }
        )
    )


def test_builds_annotation_ready_corpus(tmp_path: Path) -> None:
    result = EvaluationCorpusBuilder(FakeProvider()).build(
        CorpusBuildConfig(task="clause-summary", version="local-1", count=1),
        tmp_path,
    )
    payload = json.loads(result.dataset_path.read_text())
    manifest = yaml.safe_load(result.manifest_path.read_text())
    assert payload["examples"][0]["annotation_status"] == "proposed"
    assert payload["examples"][0]["expected"] == {}
    assert manifest["clauses"][0]["clause"]["content_hash"]
    assert manifest["statistics"]["eligible_occurrences"] == 1


def test_runs_complete_prompt_model_matrix_and_writes_redacted_report(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _write_resources(resources)
    manifest = BenchmarkManifest(
        task="clause-summary",
        dataset_version="1.0.0",
        prompt_versions=("1.0.0",),
        models=("model-a", "model-b"),
        resources=resources,
        output=tmp_path / "out",
    )
    result = EvaluationMatrixRunner(EvaluationRunner(FakeGateway())).run(manifest)
    assert [run.model for run in result.runs] == ["model-a", "model-b"]
    path = EvaluationReporter().write_matrix_summary(
        result.runs,
        manifest.output / "matrix-summary.json",
        manifest_hash=result.manifest_hash,
    )
    report = json.loads(path.read_text())
    assert report["contains_case_content"] is False
    assert "output" not in report["runs"][0]["cases"][0]
    assert report["benchmark_manifest_hash"] == manifest.fingerprint()


def test_builds_representative_stratified_corpus_with_population_statistics(
    tmp_path: Path,
) -> None:
    clauses = tuple(
        ClauseDescriptor(
            id=f"DOC-{index}",
            document_key="A" if index < 5 else "B",
            reference=f"DOC:{index + 1}",
            clause_reference=(f"1.{index + 1}" if index % 2 else str(index + 1)),
            content_hash="sha256:" + f"{index:064x}",
            clause_type=(ClauseType.REQUIREMENT if index % 3 else ClauseType.CLAUSE),
            title=None if index % 4 == 0 else f"Clause {index + 1}",
            text="x" * (50 if index < 3 else 300 if index < 7 else 900),
        )
        for index in range(10)
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return clauses

        def sample_clauses(self, **kwargs):
            raise AssertionError("representative sampling must use the full population")

    config = CorpusBuildConfig(
        task="statement-function-classification",
        version="1.0.0",
        corpus_id="semantic-roles-v1",
        knowledge_domain="functional-safety",
        count=6,
        strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        seed=17,
        include_text=False,
    )
    first = EvaluationCorpusBuilder(Provider()).build(config, tmp_path / "first")
    second = EvaluationCorpusBuilder(Provider()).build(config, tmp_path / "second")

    first_manifest = yaml.safe_load(first.manifest_path.read_text())
    second_manifest = yaml.safe_load(second.manifest_path.read_text())
    assert first_manifest == second_manifest
    assert first_manifest["statistics"]["eligible_occurrences"] == 10
    assert first_manifest["statistics"]["selected_occurrences"] == 6
    assert set(first_manifest["statistics"]["selected_dimensions"]) == {
        "clause_type",
        "document",
        "hierarchy_depth",
        "length_class",
        "structural_role",
        "title_presence",
    }
    assert all(
        item["clause"]["knowledge_domain"] == "functional-safety"
        for item in first_manifest["clauses"]
    )
    dataset = json.loads(first.dataset_path.read_text())
    assert "text" not in dataset["examples"][0]["input"]["content"]


def test_excludes_empty_content_and_separates_content_from_context(tmp_path: Path) -> None:
    shared_hash = "sha256:" + "c" * 64
    clauses = (
        ClauseDescriptor(
            id="DOC:heading",
            document_key="DOC",
            reference="DOC:1",
            clause_reference="1",
            content_hash="sha256:" + "0" * 64,
            clause_type=ClauseType.CLAUSE,
            title="Heading only",
            text="   ",
        ),
        ClauseDescriptor(
            id="DOC:1",
            document_key="DOC",
            reference="DOC:1.1",
            clause_reference="1.1",
            content_hash=shared_hash,
            clause_type=ClauseType.REQUIREMENT,
            title="First context",
            text="Same content",
        ),
        ClauseDescriptor(
            id="DOC:2",
            document_key="DOC",
            reference="DOC:2.1",
            clause_reference="2.1",
            content_hash=shared_hash,
            clause_type=ClauseType.REQUIREMENT,
            title="Second context",
            text="Same content",
        ),
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return clauses

    result = EvaluationCorpusBuilder(Provider()).build(
        CorpusBuildConfig(
            task="statement-function-classification",
            version="1.0.0",
            count=2,
            strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
            seed=3,
        ),
        tmp_path,
    )
    dataset = json.loads(result.dataset_path.read_text())
    manifest = yaml.safe_load(result.manifest_path.read_text())

    assert all(
        example["input"]["content"]["text"] == "Same content" for example in dataset["examples"]
    )
    assert {example["input"]["context"]["title"] for example in dataset["examples"]} == {
        "First context",
        "Second context",
    }
    assert manifest["statistics"]["total_occurrences"] == 3
    assert manifest["statistics"]["ineligible_empty_content"] == 1
    assert manifest["statistics"]["eligible_occurrences"] == 2
    assert manifest["statistics"]["unique_contents"] == 1
    assert manifest["statistics"]["selected_unique_contents"] == 1
    assert list(manifest["duplicate_content_groups"]) == [shared_hash]


def test_excludes_composed_family_copies_and_uses_readable_duplicate_labels(
    tmp_path: Path,
) -> None:
    shared_hash = "sha256:" + "d" * 64
    first = ClauseDescriptor(
        id="clause-a",
        document_key="IEC61508-1",
        reference="IEC 61508-1:7.4.2",
        clause_reference="7.4.2",
        content_hash=shared_hash,
        clause_type=ClauseType.REQUIREMENT,
        title="Requirements",
        text="The requirement shall be documented.",
    )
    family_copy = first.model_copy(update={"document_key": "IEC61508"})
    second = ClauseDescriptor(
        id="clause-b",
        document_key="IEC61508-2",
        reference="IEC 61508-2:7.4.2",
        clause_reference="7.4.2",
        content_hash=shared_hash,
        clause_type=ClauseType.REQUIREMENT,
        title="Software requirements",
        text="The requirement shall be documented.",
    )
    family_second_copy = second.model_copy(update={"document_key": "IEC61508"})

    class Provider:
        def list_clauses(self, **kwargs):
            return (first, family_copy, second, family_second_copy)

    result = EvaluationCorpusBuilder(Provider()).build(
        CorpusBuildConfig(
            task="statement-function-classification",
            version="1.0.0",
            count=2,
            strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
            seed=3,
        ),
        tmp_path,
    )
    manifest = yaml.safe_load(result.manifest_path.read_text())

    assert manifest["statistics"]["duplicate_document_occurrences"] == 2
    assert manifest["statistics"]["eligible_occurrences"] == 2
    labels = manifest["duplicate_content_groups"][shared_hash]
    assert labels == [
        "IEC61508-1:7.4.2 — Requirements [clause-a]",
        "IEC61508-2:7.4.2 — Software requirements [clause-b]",
    ]
    assert all(not label.startswith("IEC61508:") for label in labels)


def test_excludes_table_dominant_clauses_and_reports_reason(tmp_path: Path) -> None:
    from standards_atlas.application.semantic_qualification.clause_access import (
        ClauseContentProfile,
    )

    prose = ClauseDescriptor(
        id="DOC:1",
        document_key="DOC",
        reference="DOC:1",
        clause_reference="1",
        content_hash="sha256:" + "1" * 64,
        clause_type=ClauseType.REQUIREMENT,
        text="The supplier shall review the plan.",
    )
    table = ClauseDescriptor(
        id="DOC:A",
        document_key="DOC",
        reference="DOC:A",
        clause_reference="A",
        content_hash="sha256:" + "2" * 64,
        clause_type=ClauseType.CLAUSE,
        title="Technique selection matrix",
        text="Technique | SIL 1 | SIL 2\nFormal methods | R | HR",
        content_profile=ClauseContentProfile.TABLE_DOMINANT,
        table_block_count=1,
        table_text_length=240,
        non_table_text_length=20,
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return (prose, table)

    result = EvaluationCorpusBuilder(Provider()).build(
        CorpusBuildConfig(
            task="statement-function-classification",
            version="1.0.0",
            count=1,
        ),
        tmp_path,
    )
    dataset = json.loads(result.dataset_path.read_text())
    manifest = yaml.safe_load(result.manifest_path.read_text())

    assert [example["id"] for example in dataset["examples"]] == ["DOC:1"]
    assert manifest["statistics"]["ineligible_table_dominant_content"] == 1
    assert manifest["statistics"]["eligible_occurrences"] == 1
    assert manifest["exclusions"] == {
        "table_dominant": ["DOC:A — Technique selection matrix [DOC:A]"]
    }


def test_can_explicitly_include_table_dominant_clauses(tmp_path: Path) -> None:
    from standards_atlas.application.semantic_qualification.clause_access import (
        ClauseContentProfile,
    )

    table = ClauseDescriptor(
        id="DOC:A",
        document_key="DOC",
        reference="DOC:A",
        clause_reference="A",
        content_hash="sha256:" + "3" * 64,
        clause_type=ClauseType.CLAUSE,
        text="Technique | SIL 1 | SIL 2\nFormal methods | R | HR",
        content_profile=ClauseContentProfile.TABLE_DOMINANT,
        table_block_count=1,
        table_text_length=240,
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return (table,)

    result = EvaluationCorpusBuilder(Provider()).build(
        CorpusBuildConfig(
            task="structured-table-extraction",
            version="1.0.0",
            count=1,
            exclude_table_dominant=False,
        ),
        tmp_path,
    )
    dataset = json.loads(result.dataset_path.read_text())
    manifest = yaml.safe_load(result.manifest_path.read_text())

    assert dataset["examples"][0]["input"]["context"]["content_profile"] == ("table_dominant")
    assert dataset["examples"][0]["input"]["context"]["table_block_count"] == 1
    assert manifest["statistics"]["ineligible_table_dominant_content"] == 0
    assert manifest["exclusions"] == {}


def test_corpus_records_nearest_first_ancestor_headings(tmp_path: Path) -> None:
    clauses = (
        ClauseDescriptor(
            id="DOC:1",
            document_key="DOC",
            reference="DOC:1",
            clause_reference="1",
            content_hash="sha256:" + "1" * 64,
            clause_type=ClauseType.CLAUSE,
            title="Scope",
            text="Scope introduction.",
        ),
        ClauseDescriptor(
            id="DOC:1.1",
            document_key="DOC",
            reference="DOC:1.1",
            clause_reference="1.1",
            content_hash="sha256:" + "2" * 64,
            clause_type=ClauseType.CLAUSE,
            title=None,
            text="This document applies to software.",
            parent_id="DOC:1",
        ),
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return clauses

    result = EvaluationCorpusBuilder(Provider()).build(
        CorpusBuildConfig(
            task="statement-function-classification",
            version="scope-context",
            count=2,
        ),
        tmp_path,
    )
    dataset = json.loads(result.dataset_path.read_text())
    child = next(item for item in dataset["examples"] if item["id"] == "DOC:1.1")
    assert child["input"]["context"]["ancestor_headings"] == [
        {"clause_id": "DOC:1", "reference": "1", "title": "Scope"}
    ]


def test_corpus_preserves_materialized_structural_context(tmp_path: Path) -> None:
    class StructuralProvider:
        def list_clauses(self, **kwargs):
            return self.sample_clauses(**kwargs)

        def sample_clauses(self, **kwargs):
            return (
                ClauseDescriptor(
                    id="DOC:2",
                    document_key="DOC",
                    reference="DOC:2",
                    clause_reference="2",
                    content_hash="sha256:" + "b" * 64,
                    clause_type=ClauseType.REQUIREMENT,
                    text="Verification evidence shall be recorded.",
                    structural_context={
                        "node_kind": "leaf",
                        "sibling": {
                            "index": 1,
                            "count": 3,
                            "is_first": False,
                            "is_last": False,
                            "previous_clause_id": "DOC:1",
                            "next_clause_id": "DOC:3",
                        },
                        "references": [],
                        "scope_mentions": [
                            {
                                "source": "content",
                                "surface_text": "following two clauses",
                                "direction_hint": "forward",
                                "cardinality": 2,
                                "status": "resolved",
                            }
                        ],
                        "scopes": [],
                    },
                    reference_mentions=(),
                ),
            )

    result = EvaluationCorpusBuilder(StructuralProvider()).build(
        CorpusBuildConfig(task="clause-summary", version="local-structural", count=1),
        tmp_path,
    )
    payload = json.loads(result.dataset_path.read_text())
    context = payload["examples"][0]["input"]["context"]

    assert context["structural_context"]["node_kind"] == "leaf"
    assert context["structural_context"]["sibling"]["index"] == 1
    assert context["structural_context"]["scope_mentions"][0]["cardinality"] == 2
