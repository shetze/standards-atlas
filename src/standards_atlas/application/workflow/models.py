"""Stable workflow planning and execution data structures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowTask(StrEnum):
    DOCUMENTS = "documents"
    QUALIFICATION = "qualification"
    KNOWLEDGE = "knowledge"
    ENRICHMENTS = "enrichments"


class ArtifactPolicy(StrEnum):
    SOURCE = "source"
    DERIVED = "derived"
    REVIEW = "review"


class WorkflowStage(StrEnum):
    DOCLING = "docling"
    ATLASDATA = "atlasdata"
    IMPORT = "import"
    DERIVE = "derive"
    NORMALIZE = "normalize"
    REFERENCES = "references"
    ALIGN = "align"
    REVIEW = "review"
    ENRICH = "enrich"
    TAXONOMY = "taxonomy"
    CONTEXT_ENRICHMENT = "context-enrichment"
    CONTEXT_BASELINE = "context-baseline"
    ENRICHMENTS_BASELINE = "enrichments-baseline"
    MARKDOWN = "markdown"
    DOORSTOP = "doorstop"
    DOORSTOP_PUBLISH = "doorstop-publish"
    KNOWLEDGE_RESTORE = "knowledge-restore"
    KNOWLEDGE_ADOPT = "knowledge-adopt"
    KNOWLEDGE_PUBLISH = "knowledge-publish"
    CBOX_REPORT = "cbox-report"
    CORPUS_BUILD = "corpus-build"
    QUALIFICATION_MATRIX = "qualification-matrix"
    APPLICABILITY_DETAIL_ENRICHMENT = "applicability-detail-enrichment"
    APPLICABILITY_DECISION_POLICY = "applicability-decision-policy"
    SEMANTIC_EXTRACTION_QUALIFICATION = "semantic-extraction-qualification"
    QUALIFICATION_ARCHIVE = "qualification-archive"


class WorkflowOperationKind(StrEnum):
    DOORSTOP_PUBLISH = "doorstop-publish"
    DOCLING_CONVERT = "docling-convert"
    ATLASDATA_ONBOARD_DOCLING = "atlasdata-onboard-docling"
    ATLASDATA_ONBOARD_DOCLING_PARTS = "atlasdata-onboard-docling-parts"
    DOCUMENT_IMPORT = "document-import"
    DOCUMENT_DERIVE_PART = "document-derive-part"
    NORMALIZE_DOCUMENT = "normalize-document"
    REFERENCES_DETECT = "references-detect"
    ALIGN_DOCUMENT = "align-document"
    ALIGN_REVIEW_EXPORT = "align-review-export"
    DOCUMENT_ENRICH_CONTENT = "document-enrich-content"
    DOCUMENT_CLASSIFY_TAXONOMY = "document-classify-taxonomy"
    DOCUMENT_ENRICH_CONTEXT = "document-enrich-context"
    DOCUMENT_EXPORT_MARKDOWN = "document-export-markdown"
    DOCUMENT_EXPORT_DOORSTOP = "document-export-doorstop"
    EVALUATION_CORPUS_BUILD = "evaluation-corpus-build"
    EVALUATION_QUALIFICATION_MATRIX = "evaluation-qualification-matrix"
    EVALUATION_APPLICABILITY_POLICY = "evaluation-applicability-policy"
    EVALUATION_APPLICABILITY_DETAIL = "evaluation-applicability-detail"
    EVALUATION_SEMANTIC_EXTRACTION = "evaluation-semantic-extraction"
    EVALUATION_QUALIFICATION_ARCHIVE = "evaluation-qualification-archive"
    WORKFLOW_ARCHIVE_BASELINE = "workflow-archive-baseline"
    DOCUMENT_ADOPT_QUALIFICATION = "document-adopt-qualification"
    ATLASDATA_EXPORT_ENRICHMENTS = "atlasdata-export-enrichments"
    ATLASDATA_IMPORT_ENRICHMENTS = "atlasdata-import-enrichments"
    DOCUMENT_CBOX_REPORT = "document-cbox-report"


type WorkflowOperationValue = str | int | bool | tuple[str, ...] | None


@dataclass(frozen=True)
class WorkflowOperation:
    """CLI-independent application contract for one executable workflow operation."""

    kind: WorkflowOperationKind
    parameters: tuple[tuple[str, WorkflowOperationValue], ...] = ()

    @classmethod
    def create(
        cls,
        kind: WorkflowOperationKind,
        **parameters: WorkflowOperationValue,
    ) -> WorkflowOperation:
        return cls(kind=kind, parameters=tuple(parameters.items()))

    def parameter(
        self, name: str, default: WorkflowOperationValue = None
    ) -> WorkflowOperationValue:
        for key, value in self.parameters:
            if key == name:
                return value
        return default

    def with_parameters(self, **updates: WorkflowOperationValue) -> WorkflowOperation:
        merged = dict(self.parameters)
        merged.update(updates)
        return WorkflowOperation(kind=self.kind, parameters=tuple(merged.items()))

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "parameters": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in self.parameters
            },
        }


@dataclass(frozen=True)
class WorkflowStep:
    family: str
    document: str
    stage: WorkflowStage
    operation: WorkflowOperation
    artifact_policy: ArtifactPolicy
    manual_gate: bool = False
    output_paths: tuple[str, ...] = ()
    output_globs: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowPlan:
    families: tuple[str, ...]
    steps: tuple[WorkflowStep, ...]
    force: bool = False
    kept_stages: tuple[WorkflowStage, ...] = ()
    fresh_repetition_stages: tuple[WorkflowStage, ...] = ()


@dataclass(frozen=True)
class WorkflowExecutionResult:
    executed_steps: tuple[WorkflowStep, ...]
    blocked_documents: tuple[str, ...]
    blocked_families: tuple[str, ...]

    @property
    def completed(self) -> bool:
        return not self.blocked_documents and not self.blocked_families
