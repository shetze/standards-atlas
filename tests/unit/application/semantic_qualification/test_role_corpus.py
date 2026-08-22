from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor
from standards_atlas.application.semantic_qualification.role_corpus import (
    RoleCorpusBuildManifest,
    RoleCorpusCategory,
    RoleGoldenCorpus,
    RoleGoldenCorpusBuilder,
    classify_role_corpus_category,
    evaluate_role_golden_corpus,
)
from standards_atlas.domain.model import ClauseType


def clause(
    clause_id: str,
    text: str,
    *,
    table_block_count: int = 0,
) -> ClauseDescriptor:
    return ClauseDescriptor(
        id=clause_id,
        document_key="DOC",
        reference=f"DOC:{clause_id}",
        clause_reference=clause_id,
        content_hash="sha256:" + f"{len(clause_id):064x}",
        clause_type=ClauseType.REQUIREMENT,
        text=text,
        table_block_count=table_block_count,
    )


def test_role_corpus_categories_are_sampling_strata_not_gold_labels() -> None:
    assert (
        classify_role_corpus_category(clause("1", "The supplier is responsible for the plan."))
        is RoleCorpusCategory.EXPLICIT_RELATION
    )
    assert (
        classify_role_corpus_category(clause("2", "The analysis shall be verified."))
        is RoleCorpusCategory.PASSIVE_WITHOUT_ACTOR
    )
    assert (
        classify_role_corpus_category(clause("3", "The verifier shall validate and approve it."))
        is RoleCorpusCategory.MULTIPLE_RELATIONS
    )
    assert (
        classify_role_corpus_category(clause("4", "The authority shall remain independent."))
        is RoleCorpusCategory.ORGANIZATIONAL_RELATION
    )
    assert (
        classify_role_corpus_category(clause("5", "The supplier identifier is recorded."))
        is RoleCorpusCategory.ROLE_TERM_WITHOUT_RELATION
    )
    assert (
        classify_role_corpus_category(clause("6", "The value is recorded."))
        is RoleCorpusCategory.NEGATIVE
    )
    assert (
        classify_role_corpus_category(clause("7", "Role: Verifier", table_block_count=1))
        is RoleCorpusCategory.STRUCTURED_TABLE
    )


def test_builds_reproducible_role_golden_review_corpus(tmp_path: Path) -> None:
    clauses = (
        clause("1", "The supplier is responsible for the plan."),
        clause("2", "The analysis shall be verified."),
        clause("3", "The verifier shall validate and approve it."),
        clause("4", "The authority shall remain independent."),
        clause("5", "The supplier identifier is recorded."),
        clause("6", "The value is recorded."),
        clause("7", "Role: Verifier", table_block_count=1),
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return clauses

    manifest = RoleCorpusBuildManifest(
        corpus_id="roles-v1",
        corpus_version="1.0.0",
        quotas={category: 1 for category in RoleCorpusCategory},
        seed=42,
    )
    result = RoleGoldenCorpusBuilder(Provider()).build(manifest, tmp_path)
    dataset = json.loads(result.dataset_path.read_text())
    golden = yaml.safe_load(result.golden_path.read_text())
    build_manifest = yaml.safe_load(result.manifest_path.read_text())

    assert result.selected_count == 7
    assert not result.shortfalls
    assert len(dataset["examples"]) == 7
    assert all(example["expected"] == {} for example in dataset["examples"])
    assert {case["status"] for case in golden["cases"]} == {"proposed"}
    assert all(case["expected"] is None for case in golden["cases"])
    assert build_manifest["category_counts"] == {
        category.value: 1 for category in sorted(RoleCorpusCategory, key=lambda item: item.value)
    }


def test_role_corpus_allows_same_clause_id_in_different_documents(tmp_path: Path) -> None:
    clauses = (
        ClauseDescriptor(
            **{
                **clause("1", "The supplier is responsible for the plan.").model_dump(),
                "document_key": "DOC-A",
                "reference": "DOC-A:1",
            }
        ),
        ClauseDescriptor(
            **{
                **clause("1", "The authority shall remain independent.").model_dump(),
                "document_key": "DOC-B",
                "reference": "DOC-B:1",
            }
        ),
    )

    class Provider:
        def list_clauses(self, **kwargs):
            return clauses

    manifest = RoleCorpusBuildManifest(
        corpus_id="roles-v1",
        corpus_version="1.0.0",
        quotas={
            RoleCorpusCategory.EXPLICIT_RELATION: 1,
            RoleCorpusCategory.ORGANIZATIONAL_RELATION: 1,
        },
        seed=42,
    )
    result = RoleGoldenCorpusBuilder(Provider()).build(manifest, tmp_path)
    dataset = json.loads(result.dataset_path.read_text())
    golden = RoleGoldenCorpus.load(result.golden_path)

    assert len(golden.cases) == 2
    assert {example["id"] for example in dataset["examples"]} == {"DOC-A:1", "DOC-B:1"}


def test_golden_regression_scores_presence_and_complete_tuples(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.yaml"
    golden_path.write_text(
        """
schema_version: '1.0'
corpus_id: roles-v1
task: role-relation-extraction
corpus_version: 1.0.0
knowledge_domain: functional-safety
cases:
  - clause_id: c1
    document_key: DOC
    reference: DOC:1
    content_hash: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    category: explicit_relation
    status: published
    expected:
      role_semantics_present: true
      relations:
        - actor: Verifier
          relation: verifies
          target: analysis
          evidence: The verifier verifies the analysis.
  - clause_id: c2
    document_key: DOC
    reference: DOC:2
    content_hash: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    category: negative
    status: published
    expected:
      role_semantics_present: false
      relations: []
""".lstrip()
    )
    golden = RoleGoldenCorpus.load(golden_path)
    report = evaluate_role_golden_corpus(
        golden,
        {
            "clauses": [
                {
                    "document_key": "DOC",
                    "clause_id": "c1",
                    "role_semantics_present": True,
                    "role_relation_consensus": [
                        {
                            "actor": "verifier",
                            "relation": "verifies",
                            "target": "Analysis",
                            "support": 0.8,
                            "evidence": ["The verifier verifies the analysis."],
                        }
                    ],
                },
                {
                    "document_key": "DOC",
                    "clause_id": "c2",
                    "role_semantics_present": False,
                    "role_relation_consensus": [],
                },
            ]
        },
    )
    assert report.presence_accuracy == 1.0
    assert report.presence_f1 == 1.0
    assert report.tuple_f1 == 1.0
    assert report.exact_tuple_matches == 1


def test_published_gold_requires_expected_annotation() -> None:
    payload = {
        "schema_version": "1.0",
        "corpus_id": "roles-v1",
        "task": "role-relation-extraction",
        "corpus_version": "1.0.0",
        "cases": [
            {
                "clause_id": "c1",
                "document_key": "DOC",
                "reference": "DOC:1",
                "content_hash": "sha256:" + "a" * 64,
                "category": "negative",
                "status": "published",
            }
        ],
    }
    try:
        RoleGoldenCorpus.model_validate(payload)
    except ValueError as exc:
        assert "published role golden cases require expected annotations" in str(exc)
    else:
        raise AssertionError("expected validation failure")
