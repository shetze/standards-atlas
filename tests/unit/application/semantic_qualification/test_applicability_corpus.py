from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from pydantic import ValidationError

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityDetailGoldenSeed,
    ApplicabilityGoldenCase,
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    ApplicabilityGoldenProvenance,
    _select_stratified_cases,
    build_applicability_golden_review,
    evaluate_applicability_golden_corpus,
    migrate_applicability_golden_corpus,
    publish_applicability_golden_review,
)


def _run_archive(path: Path, *, include_candidate_prompt: bool = False) -> Path:
    clauses = (
        ("c1", "This requirement applies to new systems."),
        ("c2", "The analysis shall be performed if requested."),
        ("c3", "This part applies to A but does not apply to B."),
    )
    predictions = {
        "a": ((True, "included"), (False, None), (True, "included")),
        "b": ((False, None), (False, None), (True, "excluded")),
        "c": ((True, "included"), (False, None), (True, "included")),
        "ignored": ((False, None), (False, None), (False, None)),
    }
    observations = [
        {
            "prompt_id": "applicability-clean-full",
            "cbox_frame": "full-context-v1",
            "model_id": model_id,
            "reasoning_mode_id": "disabled",
            "repetition": 1,
            "predictions": [
                {
                    "clause_key": f"DOC/{clause_id}",
                    "document_key": "DOC",
                    "clause_id": clause_id,
                    "present": values[index][0],
                    "polarity": values[index][1],
                    "confidence": 0.9,
                }
                for index, (clause_id, _) in enumerate(clauses)
            ],
        }
        for model_id, values in predictions.items()
    ]
    if include_candidate_prompt:
        candidate_values = ((False, None), (True, "included"), (False, None))
        observations.extend(
            {
                "prompt_id": "applicability-boundary-examples",
                "cbox_frame": "full-context-v1",
                "model_id": model_id,
                "reasoning_mode_id": "disabled",
                "repetition": 1,
                "predictions": [
                    {
                        "clause_key": f"DOC/{clause_id}",
                        "document_key": "DOC",
                        "clause_id": clause_id,
                        "present": candidate_values[index][0],
                        "polarity": candidate_values[index][1],
                        "confidence": 0.8,
                    }
                    for index, (clause_id, _) in enumerate(clauses)
                ],
            }
            for model_id in predictions
        )
    snapshot = {
        "schema_version": "1.0",
        "matrix_id": "applicability-test-matrix",
        "observations": observations,
    }
    dataset = {
        "examples": [
            {
                "id": clause_id,
                "input": {
                    "context": {
                        "document_key": "DOC",
                        "clause_id": clause_id,
                        "reference": clause_id[1:],
                    },
                    "content": {"text": text},
                },
            }
            for clause_id, text in clauses
        ]
    }
    manifest = {
        "models": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
            {"id": "ignored", "dimension_eligibility": {"applicability_presence": False}},
        ]
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("configuration/qualification-manifest.yaml", yaml.safe_dump(manifest))
        archive.writestr("inputs/corpus/dataset.json", json.dumps(dataset))
        archive.writestr(
            "applicability-test-matrix/applicability-predictions.json",
            json.dumps(snapshot),
        )
    return path


def test_build_publish_and_evaluate_presence_hard_cases(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip")
    result = build_applicability_golden_review(archive, tmp_path / "review")
    assert result.selected_count == 1
    assert result.review_path.parent.name == "3.0.0"
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["reference"] == "DOC:1"
    assert rows[0]["category"] == "minority_presence_disagreement"
    assert rows[0]["participating_models"] == "3"
    assert rows[0]["selection_rank"] == "1"
    assert "polarity" not in rows[0]
    rows[0]["review_status"] = "published"
    rows[0]["present"] = "true"
    with result.review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    golden = publish_applicability_golden_review(result.review_path, archive, result.golden_path)
    assert len(golden.cases) == 1
    assert golden.schema_version == "3.0"
    assert golden.corpus_version == "3.0.0"
    assert golden.cases[0].provenance is not None
    assert golden.cases[0].provenance.source_archive == archive.name
    loaded = ApplicabilityGoldenCorpus.load(result.golden_path)
    report = evaluate_applicability_golden_corpus(loaded, archive)
    assert report.schema_version == "2.0"
    assert report.golden_corpus_version == "3.0.0"
    assert report.prompt_id == "applicability-clean-full"
    assert report.cbox_frame == "full-context-v1"
    assert report.published_cases == 1
    assert report.matched_cases == 1
    assert report.missing_cases == ()
    assert report.positive_cases == 1
    assert report.negative_cases == 0
    assert report.baseline_majority.presence_accuracy == 1.0
    assert report.baseline_majority.predicted_positive_cases == 1
    assert report.baseline_majority.predicted_positive_rate == 1.0
    assert report.baseline_majority.true_positive == 1
    assert report.baseline_majority.false_negative == 0
    assert report.baseline_majority.presence_specificity == 1.0
    assert report.baseline_majority.presence_balanced_accuracy == 1.0
    assert "polarity" not in report.model_dump_json()
    metrics = {item.model_id: item for item in report.models}
    assert metrics["a"].presence_accuracy == 1.0
    assert metrics["b"].presence_accuracy == 0.0
    assert metrics["b"].false_negative == 1
    assert metrics["b"].predicted_positive_cases == 0
    assert metrics["c"].presence_accuracy == 1.0
    assert "ignored" not in metrics
    assert report.ensembles == ()
    assert {(error.evaluator_id, error.error) for error in report.errors} == {
        ("b", "false_negative")
    }


def test_evaluate_selects_one_archived_prompt(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip", include_candidate_prompt=True)
    provenance = ApplicabilityGoldenProvenance(
        source_archive=archive.name,
        source_archive_sha256="0" * 64,
    )
    golden = ApplicabilityGoldenCorpus(
        cases=(
            ApplicabilityGoldenCase(
                clause_id="c1",
                document_key="DOC",
                reference="DOC:1",
                text="This requirement applies to new systems.",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=True),
                provenance=provenance,
            ),
            ApplicabilityGoldenCase(
                clause_id="c2",
                document_key="DOC",
                reference="DOC:2",
                text="The analysis shall be performed if requested.",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=False),
                provenance=provenance,
            ),
            ApplicabilityGoldenCase(
                clause_id="c3",
                document_key="DOC",
                reference="DOC:3",
                text="This part applies to A but does not apply to B.",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=True),
                provenance=provenance,
            ),
        )
    )

    baseline = evaluate_applicability_golden_corpus(golden, archive)
    candidate = evaluate_applicability_golden_corpus(
        golden,
        archive,
        prompt_id="applicability-boundary-examples",
    )
    assert baseline.prompt_id == "applicability-clean-full"
    assert baseline.baseline_majority.presence_f1 == 1.0
    assert candidate.prompt_id == "applicability-boundary-examples"
    assert candidate.baseline_majority.presence_f1 == 0.0


def test_evaluate_rejects_unknown_prompt(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip")
    golden = ApplicabilityGoldenCorpus(cases=())
    with pytest.raises(ValueError, match="unknown applicability prompt 'missing'"):
        evaluate_applicability_golden_corpus(golden, archive, prompt_id="missing")


def test_applicability_golden_expected_is_presence_only() -> None:
    assert ApplicabilityGoldenExpected(present=True).model_dump() == {"present": True}
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected.model_validate({"present": True, "polarity": "included"})
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected.model_validate(
            {"present": True, "applicability_polarity": "included"}
        )


def _hard_case(clause_id: str, document_key: str, category: str, score: float = 0.8):
    from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
        PresenceHardCase,
    )

    return PresenceHardCase(
        document_key=document_key,
        clause_id=clause_id,
        reference=f"{document_key}:{clause_id}",
        text=clause_id,
        category=category,
        participating_models=5,
        present_count=3,
        absent_count=2,
        presence_rate=0.6,
        majority_margin=0.2,
        disagreement_score=score,
    )


def test_stratified_selector_spills_quota_and_round_robins_documents() -> None:
    cases = [
        _hard_case("b1", "DOC-A", "balanced_presence_disagreement", 1.0),
        _hard_case("b2", "DOC-A", "balanced_presence_disagreement", 0.9),
        _hard_case("b3", "DOC-B", "balanced_presence_disagreement", 0.8),
        _hard_case("m1", "DOC-C", "minority_presence_disagreement", 0.7),
        _hard_case("m2", "DOC-D", "minority_presence_disagreement", 0.6),
        _hard_case("f1", "DOC-E", "framing_sensitive_presence", 0.0),
    ]
    selected = _select_stratified_cases(cases, limit=5)
    assert len(selected) == 5
    assert len({(case.document_key, case.clause_id) for case in selected}) == 5
    balanced = [case for case in selected if case.category == "balanced_presence_disagreement"]
    assert [case.document_key for case in balanced[:2]] == ["DOC-A", "DOC-B"]
    assert any(case.category == "framing_sensitive_presence" for case in selected)


def test_build_excludes_existing_golden_cases(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip", include_candidate_prompt=True)
    provenance = ApplicabilityGoldenProvenance(
        source_archive="old.zip", source_archive_sha256="0" * 64
    )
    golden = ApplicabilityGoldenCorpus(
        cases=(
            ApplicabilityGoldenCase(
                clause_id="c1",
                document_key="DOC",
                reference="DOC:1",
                text="old",
                category="minority_presence_disagreement",
                status="published",
                expected=ApplicabilityGoldenExpected(present=True),
                provenance=provenance,
            ),
        )
    )
    golden_path = tmp_path / "golden.yaml"
    golden_path.write_text(
        yaml.safe_dump(golden.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )

    result = build_applicability_golden_review(
        archive,
        tmp_path / "review",
        golden_path=golden_path,
    )

    assert result.candidate_count == 3
    assert result.excluded_existing_count == 1
    assert result.selected_count == 2
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["clause_id"] for row in rows} == {"c2", "c3"}


def test_publish_merges_idempotently_and_rejects_conflicting_gold(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip")
    result = build_applicability_golden_review(archive, tmp_path / "review")
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["review_status"] = "published"
    rows[0]["present"] = "true"
    with result.review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    initial = publish_applicability_golden_review(result.review_path, archive, result.golden_path)
    assert len(initial.cases) == 1

    merged_path = tmp_path / "merged.yaml"
    merged = publish_applicability_golden_review(
        result.review_path, archive, merged_path, golden_path=result.golden_path
    )
    assert len(merged.cases) == 1

    rows[0]["present"] = "false"
    with result.review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="conflicting applicability gold label"):
        publish_applicability_golden_review(
            result.review_path, archive, merged_path, golden_path=result.golden_path
        )


def test_publish_rejects_polarity_era_review_columns(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip")
    result = build_applicability_golden_review(archive, tmp_path / "review")
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["polarity"] = "included"
    with result.review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="must not contain detail columns: polarity"):
        publish_applicability_golden_review(result.review_path, archive, result.golden_path)


def test_schema_30_rejects_corpus_level_run_provenance() -> None:
    with pytest.raises(ValidationError):
        ApplicabilityGoldenCorpus.model_validate(
            {
                "schema_version": "3.0",
                "corpus_id": "applicability-hard-cases",
                "corpus_version": "3.0.0",
                "source_archive": "legacy.zip",
                "source_archive_sha256": "0" * 64,
                "cases": [],
            }
        )


def test_schema_21_load_requires_explicit_migration(tmp_path: Path) -> None:
    source = tmp_path / "legacy.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2.1",
                "corpus_id": "applicability-hard-cases",
                "corpus_version": "2.1.0",
                "cases": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="applicability-corpus-migrate"):
        ApplicabilityGoldenCorpus.load(source)


def test_migrate_schema_21_preserves_presence_and_isolates_detail_seeds(tmp_path: Path) -> None:
    source = tmp_path / "legacy.yaml"
    legacy = {
        "schema_version": "2.1",
        "corpus_id": "applicability-hard-cases",
        "corpus_version": "2.1.0",
        "cases": [
            {
                "clause_id": "c2",
                "document_key": "DOC",
                "reference": "DOC:2",
                "text": "Text 2",
                "category": "minority_presence_disagreement",
                "status": "published",
                "expected": {"present": False, "polarity": None},
                "provenance": {
                    "source_archive": "run.zip",
                    "source_archive_sha256": "1" * 64,
                },
            },
            {
                "clause_id": "c1",
                "document_key": "DOC",
                "reference": "DOC:1",
                "text": "Text 1",
                "category": "polarity_disagreement",
                "status": "published",
                "expected": {"present": True, "polarity": "included"},
                "provenance": {
                    "source_archive": "run.zip",
                    "source_archive_sha256": "1" * 64,
                },
            },
            {
                "clause_id": "c3",
                "document_key": "DOC",
                "reference": "DOC:3",
                "text": "Text 3",
                "category": "framing_sensitive_presence",
                "status": "published",
                "expected": {"present": True, "polarity": None},
                "provenance": {
                    "source_archive": "run.zip",
                    "source_archive_sha256": "1" * 64,
                },
            },
        ],
    }
    source.write_text(yaml.safe_dump(legacy, sort_keys=False), encoding="utf-8")
    presence_path = tmp_path / "presence.yaml"
    detail_path = tmp_path / "detail.yaml"

    result = migrate_applicability_golden_corpus(source, presence_path, detail_path)

    assert result.migrated_cases == 3
    assert result.published_cases == 3
    assert result.detail_seed_cases == 1
    assert result.positive_cases_without_detail_seed == 1
    presence = ApplicabilityGoldenCorpus.load(presence_path)
    assert [case.clause_id for case in presence.cases] == ["c1", "c2", "c3"]
    assert [case.expected.present for case in presence.cases if case.expected] == [
        True,
        False,
        True,
    ]
    assert "polarity" not in presence_path.read_text()
    detail = ApplicabilityDetailGoldenSeed.model_validate(
        yaml.safe_load(detail_path.read_text(encoding="utf-8"))
    )
    assert len(detail.cases) == 1
    assert detail.cases[0].expected.source_polarity == "included"
    assert detail.cases[0].expected.applicability_functions == ("inclusion",)
    assert detail.cases[0].expected.annotation_scope == "partial"

    second_presence = tmp_path / "presence-second.yaml"
    second_detail = tmp_path / "detail-second.yaml"
    migrate_applicability_golden_corpus(source, second_presence, second_detail)
    assert presence_path.read_bytes() == second_presence.read_bytes()
    assert detail_path.read_bytes() == second_detail.read_bytes()
