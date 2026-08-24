from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    DocumentDescriptor,
)
from standards_atlas.application.semantic_qualification.role_corpus import (
    RoleCorpusBuildManifest,
    RoleCorpusCategory,
    RoleGoldenCorpus,
    RoleGoldenCorpusBuilder,
    classify_role_corpus_category,
    evaluate_role_golden_corpus,
    publish_role_golden_review,
)
from standards_atlas.domain.model import ClauseType, DocumentType


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


def document(key: str, clause_count: int = 1) -> DocumentDescriptor:
    return DocumentDescriptor(
        key=key,
        title=key,
        document_type=DocumentType.STANDARD,
        clause_count=clause_count,
    )


def documents_for(clauses: tuple[ClauseDescriptor, ...]) -> tuple[DocumentDescriptor, ...]:
    keys = sorted({item.document_key for item in clauses})
    return tuple(document(key, sum(item.document_key == key for item in clauses)) for key in keys)


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
        def list_documents(self):
            return documents_for(clauses)

        def list_clauses(self, **kwargs):
            return clauses

    manifest = RoleCorpusBuildManifest(
        corpus_id="roles-v1",
        corpus_version="1.0.0",
        quotas={
            category: 1
            for category in RoleCorpusCategory
            if category is not RoleCorpusCategory.NONE
        },
        seed=42,
    )
    review_root = tmp_path / "review"
    result = RoleGoldenCorpusBuilder(Provider()).build(manifest, tmp_path, review_root)
    dataset = json.loads(result.dataset_path.read_text())
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))
    build_manifest = yaml.safe_load(result.manifest_path.read_text())

    assert result.selected_count == 7
    assert not result.shortfalls
    assert result.review_created is True
    assert not result.golden_path.exists()
    assert len(dataset["examples"]) == 7
    assert all(example["expected"] == {} for example in dataset["examples"])
    assert len(review_rows) == 7
    assert {row["review_status"] for row in review_rows} == {"pending"}
    assert {row["role_semantics_present"] for row in review_rows} == {""}
    assert list(review_rows[0])[-2:] == ["clause_id", "content_hash"]
    assert build_manifest["category_counts"] == {
        category.value: 1
        for category in sorted(RoleCorpusCategory, key=lambda item: item.value)
        if category is not RoleCorpusCategory.NONE
    }


def test_role_corpus_excludes_family_aggregate_and_qualifies_part_reference(
    tmp_path: Path,
) -> None:
    aggregate = ClauseDescriptor(
        **{
            **clause("7", "The supplier is responsible for the aggregate plan.").model_dump(),
            "document_key": "EN50126",
            "reference": "EN50126:7",
            "clause_reference": "7",
        }
    )
    part = ClauseDescriptor(
        **{
            **clause("7", "The supplier is responsible for the part plan.").model_dump(),
            "document_key": "EN50126-2",
            "reference": "EN50126:7",
            "clause_reference": "7",
        }
    )
    clauses = (aggregate, part)

    class Provider:
        def list_documents(self):
            return (document("EN50126"), document("EN50126-2"))

        def list_clauses(self, **kwargs):
            return clauses

    manifest = RoleCorpusBuildManifest(
        corpus_id="roles-v1",
        corpus_version="1.0.0",
        quotas={RoleCorpusCategory.EXPLICIT_RELATION: 1},
        seed=42,
    )
    result = RoleGoldenCorpusBuilder(Provider()).build(
        manifest, tmp_path / "data", tmp_path / "review"
    )
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))

    assert len(review_rows) == 1
    assert review_rows[0]["document_key"] == "EN50126-2"
    assert review_rows[0]["reference"] == "EN50126-2:7"


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
        def list_documents(self):
            return documents_for(clauses)

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
    review_root = tmp_path / "review"
    result = RoleGoldenCorpusBuilder(Provider()).build(manifest, tmp_path, review_root)
    dataset = json.loads(result.dataset_path.read_text())
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))

    assert len(review_rows) == 2
    assert {(row["document_key"], row["clause_id"]) for row in review_rows} == {
        ("DOC-A", "1"),
        ("DOC-B", "1"),
    }
    assert {example["id"] for example in dataset["examples"]} == {"DOC-A:1", "DOC-B:1"}


def test_role_corpus_build_preserves_existing_review(tmp_path: Path) -> None:
    clauses = (clause("1", "The supplier is responsible for the plan."),)

    class Provider:
        def list_documents(self):
            return documents_for(clauses)

        def list_clauses(self, **kwargs):
            return clauses

    manifest = RoleCorpusBuildManifest(
        corpus_id="roles-v1",
        corpus_version="1.0.0",
        quotas={RoleCorpusCategory.EXPLICIT_RELATION: 1},
    )
    review_root = tmp_path / "review"
    builder = RoleGoldenCorpusBuilder(Provider())
    first = builder.build(manifest, tmp_path / "data", review_root)
    first.review_path.write_text("human edit\n", encoding="utf-8")
    second = builder.build(manifest, tmp_path / "data", review_root)

    assert second.review_created is False
    assert second.review_path.read_text(encoding="utf-8") == "human edit\n"


def test_publish_compiles_flat_review_rows_and_multiple_relations(tmp_path: Path) -> None:
    manifest_path = tmp_path / "corpus-manifest.yaml"
    manifest_path.write_text(
        "corpus_id: roles-v1\ncorpus_version: 1.0.0\nknowledge_domain: functional-safety\n",
        encoding="utf-8",
    )
    review_path = tmp_path / "role-golden-review.csv"
    fields = [
        "document_key",
        "clause_id",
        "reference",
        "category",
        "content_hash",
        "text",
        "review_status",
        "role_semantics_present",
        "actor",
        "relation_class",
        "predicate",
        "target",
        "condition",
        "evidence",
        "review_note",
    ]
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        base = {
            "document_key": "DOC",
            "clause_id": "1",
            "reference": "DOC:1",
            "category": "multiple_relations",
            "content_hash": "sha256:" + "a" * 64,
            "text": "The verifier verifies and approves the analysis.",
            "review_status": "published",
            "role_semantics_present": "true",
            "condition": "",
            "review_note": "reviewed",
        }
        writer.writerow(
            {
                **base,
                "actor": "Verifier",
                "relation_class": "performance",
                "predicate": "verify",
                "target": "analysis",
                "evidence": "verifier verifies",
            }
        )
        writer.writerow(
            {
                **base,
                "review_status": "",
                "role_semantics_present": "",
                "actor": "Verifier",
                "relation_class": "performance",
                "predicate": "approve",
                "target": "analysis",
                "evidence": "approves the analysis",
            }
        )
    output_path = tmp_path / "role-golden-corpus.yaml"
    corpus = publish_role_golden_review(review_path, manifest_path, output_path)

    assert output_path.exists()
    assert len(corpus.cases) == 1
    assert corpus.cases[0].status == "published"
    assert corpus.cases[0].expected is not None
    assert corpus.cases[0].expected.role_semantics_present is True
    assert {
        (item.relation_class, item.predicate) for item in corpus.cases[0].expected.relations
    } == {("performance", "verify"), ("performance", "approve")}


def test_publish_ignores_pending_and_rejected_rows(tmp_path: Path) -> None:
    manifest_path = tmp_path / "corpus-manifest.yaml"
    manifest_path.write_text(
        "corpus_id: roles-v1\ncorpus_version: 1.0.0\nknowledge_domain: default\n",
        encoding="utf-8",
    )
    review_path = tmp_path / "role-golden-review.csv"
    review_path.write_text(
        "document_key,clause_id,reference,category,content_hash,text,review_status,"
        "role_semantics_present,actor,relation_class,predicate,target,condition,evidence,"
        "review_note\n"
        "DOC,1,DOC:1,negative,sha256:" + "a" * 64 + ",text,pending,,,,,,,,\n"
        "DOC,2,DOC:2,negative,sha256:" + "b" * 64 + ",text,rejected,false,,,,,,,\n"
        "DOC,3,DOC:3,negative,sha256:" + "c" * 64 + ",text,published,false,,,,,,,\n",
        encoding="utf-8",
    )
    corpus = publish_role_golden_review(
        review_path, manifest_path, tmp_path / "role-golden-corpus.yaml"
    )
    assert [(case.document_key, case.clause_id) for case in corpus.cases] == [("DOC", "3")]


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
          relation_class: performance
          predicate: verify
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
                            "relation_class": "performance",
                            "predicate": "verify",
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
