from datetime import UTC, datetime
from pathlib import Path

import pytest

from standards_atlas.application.services.evaluation import (
    AnnotationContractError,
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    AnnotationResolutionSource,
    AnnotationReview,
    ClauseAnnotationPublisher,
    ClauseAnnotationRepository,
    ClauseAnnotationResolver,
    ClauseEvaluationAnnotation,
    ClauseReference,
    CorpusClause,
    CorpusManifestRepository,
    EvaluationCorpusManifest,
    ReviewDecision,
    SemanticRoleSelection,
    normalized_content_hash,
)
from standards_atlas.domain.model import SemanticRole


def clause_reference(text: str = "The system shall be verified.") -> ClauseReference:
    return ClauseReference(
        knowledge_domain="functional-safety",
        document_key="example-standard-2026",
        clause_id="example-standard-7.4.5",
        content_hash=normalized_content_hash(text),
    )


def proposal(reference: ClauseReference) -> ClauseEvaluationAnnotation:
    return ClauseEvaluationAnnotation(
        task="semantic-role-classification",
        lifecycle_status=AnnotationLifecycleStatus.PROPOSED,
        clause=reference,
        proposal=SemanticRoleSelection(
            semantic_roles=(SemanticRole.VERIFICATION,),
            primary_role=SemanticRole.VERIFICATION,
            confidence=0.91,
        ),
        generator=AnnotationGenerator(
            provider="local",
            model="example-model",
            prompt_id="semantic-role-v1",
            generated_at=datetime(2026, 7, 28, tzinfo=UTC),
        ),
    )


def reviewed(reference: ClauseReference) -> ClauseEvaluationAnnotation:
    item = proposal(reference)
    return item.model_copy(
        update={
            "lifecycle_status": AnnotationLifecycleStatus.REVIEWED,
            "annotation": item.proposal,
            "review": AnnotationReview(
                decision=ReviewDecision.ACCEPTED,
                reviewer="reviewer",
                reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            ),
        }
    )


def test_normalized_content_hash_is_deterministic_and_context_independent() -> None:
    first = normalized_content_hash("Applies to all systems.")
    second = normalized_content_hash("Applies to all systems.")
    changed = normalized_content_hash("Applies to selected systems.")

    assert first == second
    assert first.startswith("sha256:")
    assert changed != first


def test_manifest_rejects_duplicate_clause_references() -> None:
    reference = clause_reference()

    with pytest.raises(ValueError, match="unique clause references"):
        EvaluationCorpusManifest(
            corpus_id="semantic-roles-v1",
            task="semantic-role-classification",
            corpus_version="1.0.0",
            selection_strategy="stratified",
            seed=42,
            clauses=(CorpusClause(clause=reference), CorpusClause(clause=reference)),
        )


def test_repository_round_trip_is_content_safe(tmp_path: Path) -> None:
    repository = ClauseAnnotationRepository(tmp_path / "local")
    annotation = proposal(clause_reference())

    path = repository.write("semantic-roles-v1", annotation)
    loaded = repository.load("semantic-roles-v1", annotation.clause)

    assert loaded == annotation
    assert "The system shall be verified." not in path.read_text(encoding="utf-8")


def test_manifest_repository_round_trip(tmp_path: Path) -> None:
    reference = clause_reference()
    manifest = EvaluationCorpusManifest(
        corpus_id="semantic-roles-v1",
        task="semantic-role-classification",
        corpus_version="1.0.0",
        selection_strategy="stratified",
        seed=42,
        clauses=(CorpusClause(clause=reference, strata={"role": "verification"}),),
    )
    repository = CorpusManifestRepository(tmp_path)

    repository.write(manifest)

    assert repository.load(manifest.corpus_id) == manifest


def test_published_annotation_has_priority_and_reports_shadow(tmp_path: Path) -> None:
    reference = clause_reference()
    local_root = tmp_path / "local"
    data_root = tmp_path / "data"
    local_repository = ClauseAnnotationRepository(local_root)
    data_repository = ClauseAnnotationRepository(data_root)
    local_repository.write("semantic-roles-v1", proposal(reference))
    published = reviewed(reference).model_copy(
        update={"lifecycle_status": AnnotationLifecycleStatus.PUBLISHED}
    )
    data_repository.write("semantic-roles-v1", published)

    resolved = ClauseAnnotationResolver(
        local_root=local_root,
        published_root=data_root,
    ).resolve("semantic-roles-v1", reference)

    assert resolved is not None
    assert resolved.annotation == published
    assert resolved.source is AnnotationResolutionSource.PUBLISHED
    assert resolved.shadowed_local_path is not None
    assert resolved.local_differs


def test_resolver_rejects_stale_content_hash(tmp_path: Path) -> None:
    original = clause_reference()
    changed = clause_reference("The system should be verified.")
    repository = ClauseAnnotationRepository(tmp_path / "local")
    repository.write("semantic-roles-v1", proposal(original))

    resolver = ClauseAnnotationResolver(
        local_root=tmp_path / "local",
        published_root=tmp_path / "data",
    )

    with pytest.raises(AnnotationContractError, match="stale annotation content hash"):
        resolver.resolve("semantic-roles-v1", changed)


def test_publisher_accepts_only_reviewed_annotations(tmp_path: Path) -> None:
    reference = clause_reference()
    local_root = tmp_path / "local"
    data_root = tmp_path / "data"
    repository = ClauseAnnotationRepository(local_root)
    repository.write("semantic-roles-v1", proposal(reference))
    publisher = ClauseAnnotationPublisher(local_root=local_root, published_root=data_root)

    with pytest.raises(AnnotationContractError, match="only reviewed"):
        publisher.publish("semantic-roles-v1", reference)

    repository.write("semantic-roles-v1", reviewed(reference))
    target = publisher.publish("semantic-roles-v1", reference)

    published = ClauseAnnotationRepository(data_root).load_path(target)
    assert published.lifecycle_status is AnnotationLifecycleStatus.PUBLISHED
