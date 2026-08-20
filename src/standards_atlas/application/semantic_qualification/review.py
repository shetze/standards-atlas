"""Human review workflow for generated semantic annotation proposals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationContractError,
    AnnotationLifecycleStatus,
    AnnotationReview,
    ClauseAnnotationPublisher,
    ClauseAnnotationRepository,
    ClauseEvaluationAnnotation,
    ReviewDecision,
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.references import (
    ClauseReferenceAnalysis,
    ClauseReferenceRepository,
)

_REVIEW_BLOCK = re.compile(
    r"<!-- standards-atlas-semantic-review:v1 -->\s*```yaml\s*(.*?)\s*```",
    re.DOTALL,
)


class ReviewForm(BaseModel):
    """Editable data embedded in a local Markdown review document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    clause_key: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: ReviewDecision = ReviewDecision.ACCEPTED
    statement_functions: tuple[str, ...] = ()
    primary_function: str | None = None
    knowledge_kinds: tuple[str, ...] = ()
    primary_knowledge_kind: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reviewer: str = ""
    reviewed_at: datetime | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> ReviewForm:
        if (
            self.primary_function is not None
            and self.primary_function not in self.statement_functions
        ):
            raise ValueError("primary_function must be included in statement_functions")
        if len(set(self.statement_functions)) != len(self.statement_functions):
            raise ValueError("statement_functions must not contain duplicates")
        if (
            self.primary_knowledge_kind is not None
            and self.primary_knowledge_kind not in self.knowledge_kinds
        ):
            raise ValueError("primary_knowledge_kind must be included in knowledge_kinds")
        if len(set(self.knowledge_kinds)) != len(self.knowledge_kinds):
            raise ValueError("knowledge_kinds must not contain duplicates")
        return self


@dataclass(frozen=True)
class ReviewExportResult:
    exported: int
    skipped: int
    review_directory: Path


@dataclass(frozen=True)
class ReviewImportResult:
    imported: int
    skipped: int
    annotation_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ReviewPublishResult:
    published: int
    annotation_paths: tuple[Path, ...]
    manifest_path: Path | None


class SemanticAnnotationReviewService:
    """Export proposals to Markdown and import human decisions as reviewed annotations."""

    def export_run(
        self,
        *,
        run_directory: Path,
        review_directory: Path,
        overwrite: bool = False,
        reference_root: Path | None = None,
    ) -> ReviewExportResult:
        candidates = tuple(_candidate_paths(run_directory))
        if not candidates:
            raise AnnotationContractError(
                f"no proposal candidates found below run directory: {run_directory}"
            )
        exported = skipped = 0
        for candidate_path in candidates:
            candidate = _load_candidate(candidate_path)
            target = review_directory / f"{candidate.clause.clause_id}.md"
            if target.exists() and not overwrite:
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            references = (
                ClauseReferenceRepository(reference_root).load_for_key(candidate.clause.key)
                if reference_root is not None
                else None
            )
            target.write_text(
                _render_review(candidate, _load_clause_context(candidate_path), references),
                encoding="utf-8",
            )
            exported += 1
        return ReviewExportResult(exported, skipped, review_directory)

    def import_reviews(
        self,
        *,
        review_directory: Path,
        run_directory: Path,
        local_corpus_root: Path,
        corpus_id: str,
        overwrite: bool = False,
    ) -> ReviewImportResult:
        repository = ClauseAnnotationRepository(local_corpus_root)
        candidates = {
            candidate.clause.key: candidate
            for path in _candidate_paths(run_directory)
            for candidate in (_load_candidate(path),)
        }
        if not candidates:
            raise AnnotationContractError(
                f"no proposal candidates found below run directory: {run_directory}"
            )

        imported = skipped = 0
        written: list[Path] = []
        seen: set[str] = set()
        for review_path in sorted(review_directory.glob("*.md")):
            form = _parse_review(review_path)
            if form.clause_key in seen:
                raise AnnotationContractError(
                    f"duplicate review for clause {form.clause_key}: {review_path}"
                )
            seen.add(form.clause_key)
            candidate = candidates.get(form.clause_key)
            if candidate is None:
                raise AnnotationContractError(
                    f"review does not match a proposal in the run: {review_path}"
                )
            if form.content_hash != candidate.clause.content_hash:
                raise AnnotationContractError(f"stale review content hash: {review_path}")
            reviewed = _apply_review(candidate, form, review_path)
            target = repository.path_for(corpus_id, reviewed.clause)
            if target.exists() and not overwrite:
                existing = repository.load_path(target)
                if existing == reviewed:
                    skipped += 1
                    continue
                raise AnnotationContractError(
                    f"reviewed annotation already exists with different content: {target}"
                )
            written.append(repository.write(corpus_id, reviewed))
            imported += 1
        if imported == 0 and skipped == 0:
            raise AnnotationContractError(f"no Markdown reviews found: {review_directory}")
        return ReviewImportResult(imported, skipped, tuple(written))

    def publish_reviews(
        self,
        *,
        corpus_id: str,
        local_corpus_root: Path,
        published_corpus_root: Path,
        publish_manifest: bool = True,
    ) -> ReviewPublishResult:
        local = ClauseAnnotationRepository(local_corpus_root)
        publisher = ClauseAnnotationPublisher(
            local_root=local_corpus_root,
            published_root=published_corpus_root,
        )
        annotation_root = local_corpus_root / corpus_id / "annotations"
        paths: list[Path] = []
        for source in sorted(annotation_root.rglob("*.yaml")) if annotation_root.exists() else ():
            annotation = local.load_path(source)
            if annotation.lifecycle_status is not AnnotationLifecycleStatus.REVIEWED:
                continue
            paths.append(publisher.publish(corpus_id, annotation.clause))
        manifest_path = None
        if publish_manifest:
            manifest_path = publisher.publish_manifest(corpus_id)
        return ReviewPublishResult(len(paths), tuple(paths), manifest_path)


def _candidate_paths(run_directory: Path):
    yield from sorted(run_directory.glob("*/evaluation.yaml"))
    yield from sorted(run_directory.glob("*/evaluation.json"))


def _load_candidate(path: Path) -> ClauseEvaluationAnnotation:
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    candidate_payload = payload.get("annotation_candidate", payload)
    candidate = ClauseEvaluationAnnotation.model_validate(candidate_payload)
    if candidate.lifecycle_status is not AnnotationLifecycleStatus.PROPOSED:
        raise AnnotationContractError(f"review source is not a proposal: {path}")
    return candidate


def _load_clause_context(candidate_path: Path) -> dict[str, Any]:
    request_path = candidate_path.with_name("request.json")
    if not request_path.exists():
        return {}
    payload = json.loads(request_path.read_text(encoding="utf-8"))

    context: dict[str, Any] = {}
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        clause_context = metadata.get("clause_context")
        if isinstance(clause_context, dict):
            context.update(clause_context)

    # Proposal runs persist StructuredGenerationRequest fields directly. Keep
    # compatibility with older Chat Completions-shaped request artifacts too.
    user_prompt = payload.get("user_prompt")
    if isinstance(user_prompt, str) and user_prompt.strip():
        context["rendered_prompt"] = user_prompt
        context.update(_structural_context_from_prompt(user_prompt))
        return context

    messages = payload.get("messages", ())
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                context["rendered_prompt"] = content
                context.update(_structural_context_from_prompt(content))
                return context
    return context


def _structural_context_from_prompt(prompt: str) -> dict[str, Any]:
    marker = "Structural context:"
    if marker not in prompt:
        return {}
    raw = prompt.rsplit(marker, maxsplit=1)[1].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _render_review(
    candidate: ClauseEvaluationAnnotation,
    context: dict[str, Any],
    references: ClauseReferenceAnalysis | None = None,
) -> str:
    proposal = candidate.proposal
    form = ReviewForm(
        clause_key=candidate.clause.key,
        content_hash=candidate.clause.content_hash,
        decision=ReviewDecision.ACCEPTED,
        statement_functions=tuple(role.value for role in proposal.statement_functions),
        primary_function=proposal.primary_function.value if proposal.primary_function else None,
        knowledge_kinds=tuple(kind.value for kind in proposal.knowledge_kinds),
        primary_knowledge_kind=(
            proposal.primary_knowledge_kind.value if proposal.primary_knowledge_kind else None
        ),
        confidence=proposal.confidence,
    )
    editable = yaml.safe_dump(form.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    rationale = proposal.rationale or "—"
    prompt = context.get("rendered_prompt") or "Clause text unavailable; inspect the local corpus."
    reference = str(context.get("reference") or candidate.clause.clause_id)
    title = context.get("title")
    readable_clause = f"{candidate.clause.document_key} — {reference}"
    if isinstance(title, str) and title.strip():
        readable_clause += f" {title.strip()}"
    return (
        f"# Semantic annotation review: {readable_clause}\n\n"
        f"- Knowledge domain: `{candidate.clause.knowledge_domain}`\n"
        f"- Document: `{candidate.clause.document_key}`\n"
        f"- Clause reference: `{reference}`\n"
        + (f"- Clause title: {title.strip()}\n" if isinstance(title, str) and title.strip() else "")
        + f"- Stable clause key: `{candidate.clause.key}`\n"
        f"- Content hash: `{candidate.clause.content_hash}`\n"
        f"- Generator: `{candidate.generator.provider}/{candidate.generator.model}`\n"
        f"- Prompt: `{candidate.generator.prompt_id}`\n\n"
        "## Local review context\n\n"
        f"```text\n{prompt}\n```\n\n" + _render_references(references) + "## Generated proposal\n\n"
        f"- Roles: {', '.join(role.value for role in proposal.statement_functions) or 'none'}\n"
        f"- Knowldg kinds: {', '.join(kind.value for kind in proposal.knowledge_kinds) or 'none'}\n"
        "- Primary knowledge kind: "
        f"{proposal.primary_knowledge_kind.value if proposal.primary_knowledge_kind else 'none'}\n"
        "- Primary role: "
        f"{proposal.primary_function.value if proposal.primary_function else 'none'}\n"
        f"- Confidence: {proposal.confidence if proposal.confidence is not None else 'none'}\n"
        f"- Rationale: {rationale}\n\n"
        "## Review data\n\n"
        "Edit only the YAML block. Set `reviewer` and optionally `reviewed_at`; "
        "the importer uses the current UTC time when `reviewed_at` is empty.\n\n"
        "<!-- standards-atlas-semantic-review:v1 -->\n"
        f"```yaml\n{editable}```\n"
    )


def _render_references(analysis: ClauseReferenceAnalysis | None) -> str:
    if analysis is None or not analysis.references:
        return ""
    lines = ["## Resolved clause references", ""]
    for occurrence in analysis.references:
        lines.extend(
            (
                f"### {occurrence.surface_text}",
                "",
                f"- Kind: `{occurrence.kind.value}`",
                f"- Resolution: `{occurrence.status.value}`",
            )
        )
        if occurrence.targets:
            lines.append("- Targets:")
            for target in occurrence.targets:
                readable = target.reference
                if target.title:
                    readable += f" — {target.title}"
                lines.append(f"  - `{target.clause_id}`: {readable}")
        if occurrence.unresolved_references:
            unresolved = ", ".join(occurrence.unresolved_references)
            lines.append(f"- Unresolved: `{unresolved}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def _parse_review(path: Path) -> ReviewForm:
    match = _REVIEW_BLOCK.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise AnnotationContractError(f"missing embedded semantic review data: {path}")
    try:
        payload = yaml.safe_load(match.group(1))
        return ReviewForm.model_validate(payload)
    except (ValueError, yaml.YAMLError) as exc:
        raise AnnotationContractError(f"invalid embedded review data in {path}: {exc}") from exc


def _apply_review(
    candidate: ClauseEvaluationAnnotation,
    form: ReviewForm,
    path: Path,
) -> ClauseEvaluationAnnotation:
    reviewer = form.reviewer.strip()
    if not reviewer:
        raise AnnotationContractError(f"reviewer must be set: {path}")
    selection = StatementFunctionSelection.model_validate(
        {
            "statement_functions": form.statement_functions,
            "primary_function": form.primary_function,
            "knowledge_kinds": form.knowledge_kinds,
            "primary_knowledge_kind": form.primary_knowledge_kind,
            "confidence": form.confidence,
        }
    )
    if form.decision is ReviewDecision.ACCEPTED and selection != candidate.proposal.model_copy(
        update={"rationale": None}
    ):
        candidate_without_rationale = candidate.proposal.model_copy(update={"rationale": None})
        if selection != candidate_without_rationale:
            raise AnnotationContractError(
                f"accepted review must preserve the generated selection: {path}"
            )
    if form.decision is ReviewDecision.CORRECTED and selection == candidate.proposal.model_copy(
        update={"rationale": None}
    ):
        raise AnnotationContractError(f"corrected review must change the proposal: {path}")
    if form.decision is ReviewDecision.REJECTED and selection.statement_functions:
        raise AnnotationContractError(
            f"rejected review must not select statement functions: {path}"
        )
    return candidate.model_copy(
        update={
            "lifecycle_status": AnnotationLifecycleStatus.REVIEWED,
            "annotation": selection,
            "review": AnnotationReview(
                decision=form.decision,
                reviewer=reviewer,
                reviewed_at=form.reviewed_at or datetime.now(UTC),
                comment=form.comment,
            ),
        }
    )
