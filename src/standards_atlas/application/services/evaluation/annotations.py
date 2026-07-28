"""Contracts and services for reproducible clause evaluation annotations."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model import SemanticRole


class AnnotationLifecycleStatus(StrEnum):
    """Lifecycle state of a corpus annotation."""

    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    PUBLISHED = "published"


class AnnotationResolutionSource(StrEnum):
    """Origin selected by the annotation resolver."""

    PUBLISHED = "published"
    LOCAL_REVIEWED = "local_reviewed"
    LOCAL_PROPOSAL = "local_proposal"


class ReviewDecision(StrEnum):
    """Human decision applied to a generated proposal."""

    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class ClauseReference(BaseModel):
    """Stable clause identity plus normalized-content integrity evidence."""

    model_config = ConfigDict(frozen=True)

    knowledge_domain: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def key(self) -> str:
        """Return the stable cross-file identity of this clause."""
        return f"{self.knowledge_domain}:{self.document_key}:{self.clause_id}"


class SemanticRoleSelection(BaseModel):
    """Semantic-role classification assigned to a clause."""

    model_config = ConfigDict(frozen=True)

    semantic_roles: tuple[SemanticRole, ...] = ()
    primary_role: SemanticRole | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None

    @model_validator(mode="after")
    def primary_role_must_be_selected(self) -> SemanticRoleSelection:
        if self.primary_role is not None and self.primary_role not in self.semantic_roles:
            raise ValueError("primary_role must be included in semantic_roles")
        if len(set(self.semantic_roles)) != len(self.semantic_roles):
            raise ValueError("semantic_roles must not contain duplicates")
        return self


class AnnotationGenerator(BaseModel):
    """Provenance of a generated annotation proposal."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    generated_at: datetime
    task_version: str = "1.0.0"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None
    input_hash: str | None = None
    raw_response_hash: str | None = None


class AnnotationReview(BaseModel):
    """Human review evidence for an annotation proposal."""

    model_config = ConfigDict(frozen=True)

    decision: ReviewDecision
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    comment: str | None = None


class ClauseEvaluationAnnotation(BaseModel):
    """Versioned proposal and optional reviewed annotation for one clause."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    task: str = Field(min_length=1)
    lifecycle_status: AnnotationLifecycleStatus
    clause: ClauseReference
    proposal: SemanticRoleSelection
    generator: AnnotationGenerator
    annotation: SemanticRoleSelection | None = None
    review: AnnotationReview | None = None

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> ClauseEvaluationAnnotation:
        if self.lifecycle_status is AnnotationLifecycleStatus.PROPOSED:
            if self.annotation is not None or self.review is not None:
                raise ValueError("proposed annotations must not contain review results")
            return self
        if self.annotation is None or self.review is None:
            raise ValueError("reviewed and published annotations require annotation and review")
        return self


class CorpusClause(BaseModel):
    """Content-safe member reference in a reproducible corpus manifest."""

    model_config = ConfigDict(frozen=True)

    clause: ClauseReference
    strata: dict[str, str] = Field(default_factory=dict)


class CorpusPopulationStatistics(BaseModel):
    """Eligibility, uniqueness, and stratum counts for a corpus population."""

    model_config = ConfigDict(frozen=True)

    total_occurrences: int = Field(ge=0)
    ineligible_empty_content: int = Field(ge=0)
    duplicate_document_occurrences: int = Field(default=0, ge=0)
    eligible_occurrences: int = Field(ge=0)
    unique_contents: int = Field(ge=0)
    selected_occurrences: int = Field(ge=0)
    selected_unique_contents: int = Field(ge=0)
    dimensions: dict[str, dict[str, int]] = Field(default_factory=dict)
    selected_dimensions: dict[str, dict[str, int]] = Field(default_factory=dict)


class EvaluationCorpusManifest(BaseModel):
    """Versioned declaration of a content-safe evaluation corpus."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    corpus_id: str = Field(min_length=1)
    task: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    selection_strategy: str = Field(min_length=1)
    seed: int
    filters: dict[str, Any] = Field(default_factory=dict)
    statistics: CorpusPopulationStatistics | None = None
    duplicate_content_groups: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    clauses: tuple[CorpusClause, ...]

    @model_validator(mode="after")
    def clause_references_are_unique(self) -> EvaluationCorpusManifest:
        keys = [item.clause.key for item in self.clauses]
        if len(keys) != len(set(keys)):
            raise ValueError("corpus clauses must have unique clause references")
        return self


class ResolvedClauseAnnotation(BaseModel):
    """Annotation selected from published and local stores."""

    model_config = ConfigDict(frozen=True)

    annotation: ClauseEvaluationAnnotation
    source: AnnotationResolutionSource
    path: Path
    shadowed_local_path: Path | None = None
    local_differs: bool = False


class AnnotationContractError(RuntimeError):
    """Raised when annotation persistence or publication violates the contract."""


def normalized_content_hash(text: str) -> str:
    """Hash only the normalized clause content, never structural context."""
    payload = text.encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class ClauseAnnotationRepository:
    """YAML persistence for local and published clause annotations."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, corpus_id: str, clause: ClauseReference) -> Path:
        safe_clause_id = _safe_path_component(clause.clause_id)
        return (
            self._root / corpus_id / "annotations" / clause.document_key / f"{safe_clause_id}.yaml"
        )

    def write(self, corpus_id: str, annotation: ClauseEvaluationAnnotation) -> Path:
        path = self.path_for(corpus_id, annotation.clause)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = annotation.model_dump(mode="json", exclude_none=True)
        serialized = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        path.write_text(serialized, encoding="utf-8")
        return path

    def load_path(self, path: Path) -> ClauseEvaluationAnnotation:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ClauseEvaluationAnnotation.model_validate(payload)

    def load(self, corpus_id: str, clause: ClauseReference) -> ClauseEvaluationAnnotation | None:
        path = self.path_for(corpus_id, clause)
        return self.load_path(path) if path.exists() else None


class CorpusManifestRepository:
    """YAML persistence for content-safe corpus manifests."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, corpus_id: str) -> Path:
        return self._root / corpus_id / "corpus.yaml"

    def write(self, manifest: EvaluationCorpusManifest) -> Path:
        path = self.path_for(manifest.corpus_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        serialized = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        path.write_text(serialized, encoding="utf-8")
        return path

    def load(self, corpus_id: str) -> EvaluationCorpusManifest:
        payload = yaml.safe_load(self.path_for(corpus_id).read_text(encoding="utf-8"))
        return EvaluationCorpusManifest.model_validate(payload)


class ClauseAnnotationResolver:
    """Resolve published annotations before local reviewed or proposed data."""

    def __init__(self, *, local_root: Path, published_root: Path) -> None:
        self._local = ClauseAnnotationRepository(local_root)
        self._published = ClauseAnnotationRepository(published_root)

    def resolve(
        self,
        corpus_id: str,
        clause: ClauseReference,
    ) -> ResolvedClauseAnnotation | None:
        published_path = self._published.path_for(corpus_id, clause)
        local_path = self._local.path_for(corpus_id, clause)
        published = self._published.load(corpus_id, clause)
        local = self._local.load(corpus_id, clause)

        if published is not None:
            self._validate_clause_match(clause, published, published_path)
            differs = local is not None and local.model_dump() != published.model_dump()
            return ResolvedClauseAnnotation(
                annotation=published,
                source=AnnotationResolutionSource.PUBLISHED,
                path=published_path,
                shadowed_local_path=local_path if local is not None else None,
                local_differs=differs,
            )
        if local is None:
            return None
        self._validate_clause_match(clause, local, local_path)
        source = (
            AnnotationResolutionSource.LOCAL_PROPOSAL
            if local.lifecycle_status is AnnotationLifecycleStatus.PROPOSED
            else AnnotationResolutionSource.LOCAL_REVIEWED
        )
        return ResolvedClauseAnnotation(annotation=local, source=source, path=local_path)

    @staticmethod
    def _validate_clause_match(
        expected: ClauseReference,
        annotation: ClauseEvaluationAnnotation,
        path: Path,
    ) -> None:
        if annotation.clause.key != expected.key:
            raise AnnotationContractError(f"annotation clause identity mismatch: {path}")
        if annotation.clause.content_hash != expected.content_hash:
            raise AnnotationContractError(f"stale annotation content hash: {path}")


class ClauseAnnotationPublisher:
    """Publish reviewed local annotations into the Git-trackable data store."""

    def __init__(self, *, local_root: Path, published_root: Path) -> None:
        self._local = ClauseAnnotationRepository(local_root)
        self._published = ClauseAnnotationRepository(published_root)

    def publish(self, corpus_id: str, clause: ClauseReference) -> Path:
        local_path = self._local.path_for(corpus_id, clause)
        if not local_path.exists():
            raise AnnotationContractError(f"local annotation does not exist: {local_path}")
        annotation = self._local.load_path(local_path)
        if annotation.lifecycle_status is not AnnotationLifecycleStatus.REVIEWED:
            raise AnnotationContractError("only reviewed local annotations can be published")
        if annotation.clause != clause:
            raise AnnotationContractError(f"annotation clause reference mismatch: {local_path}")

        published = annotation.model_copy(
            update={"lifecycle_status": AnnotationLifecycleStatus.PUBLISHED}
        )
        target = self._published.write(corpus_id, published)
        return target

    def publish_manifest(self, corpus_id: str) -> Path:
        source = CorpusManifestRepository(self._local.root).path_for(corpus_id)
        if not source.exists():
            raise AnnotationContractError(f"local corpus manifest does not exist: {source}")
        target = CorpusManifestRepository(self._published.root).path_for(corpus_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target


def _safe_path_component(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_." else "_" for character in value
    )
    if not safe or safe in {".", ".."}:
        raise AnnotationContractError(f"unsafe path component: {value!r}")
    return safe
