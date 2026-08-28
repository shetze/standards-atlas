from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationContractError,
    AnnotationLifecycleStatus,
    ClauseAnnotationRepository,
    ReviewDecision,
)
from standards_atlas.application.services.evaluation import SemanticAnnotationReviewService


def _proposal_run(root: Path) -> Path:
    case = root / "clause-1"
    case.mkdir(parents=True)
    annotation = {
        "schema_version": "1.0",
        "task": "statement-function-classification",
        "lifecycle_status": "proposed",
        "clause": {
            "knowledge_domain": "functional-safety",
            "document_key": "IEC61508-3",
            "clause_id": "clause-1",
            "content_hash": "sha256:" + "a" * 64,
        },
        "proposal": {
            "statement_functions": ["requirement"],
            "primary_function": "requirement",
            "confidence": 0.9,
            "rationale": "Normative language.",
        },
        "generator": {
            "provider": "codex",
            "model": "gpt",
            "prompt_id": "structure-aware-v1",
            "generated_at": "2026-07-28T20:00:00Z",
        },
    }
    (case / "evaluation.yaml").write_text(
        yaml.safe_dump({"annotation_candidate": annotation}), encoding="utf-8"
    )
    (case / "request.json").write_text(
        json.dumps(
            {
                "user_prompt": (
                    "Clause content here.\n\nStructural context:\n"
                    '{"knowledge_domain":"functional-safety",'
                    '"document_key":"IEC61508-3","clause_id":"clause-1",'
                    '"reference":"7.4.2","title":"Software safety requirements"}'
                )
            }
        ),
        encoding="utf-8",
    )
    return root


def _edit_review(path: Path, **updates) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index("```yaml") + len("```yaml")
    end = text.index("```", start)
    payload = yaml.safe_load(text[start:end])
    payload.update(updates)
    replacement = "\n" + yaml.safe_dump(payload, sort_keys=False)
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def test_export_and_import_accepted_review(tmp_path: Path) -> None:
    run = _proposal_run(tmp_path / "run")
    reviews = tmp_path / "reviews"
    service = SemanticAnnotationReviewService()

    exported = service.export_run(run_directory=run, review_directory=reviews)
    review_path = reviews / "clause-1.md"
    assert exported.exported == 1
    review_text = review_path.read_text(encoding="utf-8")
    assert "Clause content here." in review_text
    assert (
        "# Semantic annotation review: IEC61508-3 — 7.4.2 Software safety requirements"
        in review_text
    )
    assert "- Clause reference: `7.4.2`" in review_text
    assert "- Clause title: Software safety requirements" in review_text
    assert "- Stable clause key: `functional-safety:IEC61508-3:clause-1`" in review_text

    _edit_review(review_path, reviewer="Sebastian")
    imported = service.import_reviews(
        review_directory=reviews,
        run_directory=run,
        local_corpus_root=tmp_path / "local",
        corpus_id="semantic-roles-v1",
    )
    assert imported.imported == 1
    annotation = ClauseAnnotationRepository(tmp_path / "local").load_path(
        imported.annotation_paths[0]
    )
    assert annotation.lifecycle_status is AnnotationLifecycleStatus.REVIEWED
    assert annotation.review is not None
    assert annotation.review.decision is ReviewDecision.ACCEPTED


def test_export_prefers_explicit_clause_context_metadata(tmp_path: Path) -> None:
    run = _proposal_run(tmp_path / "run")
    request_path = run / "clause-1" / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "user_prompt": "Clause content here.",
                "metadata": {
                    "clause_context": {
                        "reference": "8.3.1",
                        "title": "Verification planning",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    reviews = tmp_path / "reviews"

    SemanticAnnotationReviewService().export_run(run_directory=run, review_directory=reviews)

    text = (reviews / "clause-1.md").read_text(encoding="utf-8")
    assert "IEC61508-3 — 8.3.1 Verification planning" in text
    assert "- Clause reference: `8.3.1`" in text
    assert "- Clause title: Verification planning" in text


def test_import_rejects_accepted_review_with_changed_roles(tmp_path: Path) -> None:
    run = _proposal_run(tmp_path / "run")
    reviews = tmp_path / "reviews"
    service = SemanticAnnotationReviewService()
    service.export_run(run_directory=run, review_directory=reviews)
    review_path = reviews / "clause-1.md"
    _edit_review(
        review_path,
        reviewer="Sebastian",
        statement_functions=["recommendation"],
        primary_function="recommendation",
    )

    with pytest.raises(AnnotationContractError, match="accepted review must preserve"):
        service.import_reviews(
            review_directory=reviews,
            run_directory=run,
            local_corpus_root=tmp_path / "local",
            corpus_id="semantic-roles-v1",
        )


def test_corrected_review_and_batch_publish(tmp_path: Path) -> None:
    run = _proposal_run(tmp_path / "run")
    reviews = tmp_path / "reviews"
    local = tmp_path / "local"
    data = tmp_path / "data"
    service = SemanticAnnotationReviewService()
    service.export_run(run_directory=run, review_directory=reviews)
    review_path = reviews / "clause-1.md"
    _edit_review(
        review_path,
        reviewer="Sebastian",
        decision="corrected",
        statement_functions=["recommendation"],
        primary_function="recommendation",
        comment="The clause defines verification activity.",
    )
    service.import_reviews(
        review_directory=reviews,
        run_directory=run,
        local_corpus_root=local,
        corpus_id="semantic-roles-v1",
    )
    manifest = local / "semantic-roles-v1" / "corpus.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("corpus_id: semantic-roles-v1\n", encoding="utf-8")

    published = service.publish_reviews(
        corpus_id="semantic-roles-v1",
        local_corpus_root=local,
        published_corpus_root=data,
    )
    assert published.published == 1
    result = ClauseAnnotationRepository(data).load_path(published.annotation_paths[0])
    assert result.lifecycle_status is AnnotationLifecycleStatus.PUBLISHED
    assert published.manifest_path is not None


def test_export_includes_resolved_clause_references(tmp_path: Path) -> None:
    run = _proposal_run(tmp_path / "run")
    references = tmp_path / "references"
    analysis = references / "functional-safety" / "IEC61508-3" / "clause-1.yaml"
    analysis.parent.mkdir(parents=True)
    analysis.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "knowledge_domain": "functional-safety",
                "document_key": "IEC61508-3",
                "clause_id": "clause-1",
                "clause_reference": "7.4.2",
                "references": [
                    {
                        "kind": "clause_range",
                        "surface_text": "requirements 7.4.3.2.2 to 7.4.3.2.5",
                        "start_offset": 10,
                        "end_offset": 51,
                        "range_start": "7.4.3.2.2",
                        "range_end": "7.4.3.2.5",
                        "document_scope": "same_document",
                        "status": "resolved",
                        "targets": [
                            {
                                "clause_id": "target-1",
                                "reference": "7.4.3.2.2",
                                "title": "First test goal",
                            },
                            {
                                "clause_id": "target-2",
                                "reference": "7.4.3.2.5",
                                "title": "Last test goal",
                            },
                        ],
                        "unresolved_references": [],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    reviews = tmp_path / "reviews"

    SemanticAnnotationReviewService().export_run(
        run_directory=run,
        review_directory=reviews,
        reference_root=references,
    )

    text = (reviews / "clause-1.md").read_text(encoding="utf-8")
    assert "## Resolved clause references" in text
    assert "requirements 7.4.3.2.2 to 7.4.3.2.5" in text
    assert "7.4.3.2.2 — First test goal" in text
