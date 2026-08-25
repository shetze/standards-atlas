"""Stable workflow planning and execution data structures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowTask(StrEnum):
    DOCUMENTS = "documents"
    QUALIFICATION = "qualification"


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
    ONTOLOGY = "ontology"
    COMPOSE = "compose"
    MARKDOWN = "markdown"
    DOORSTOP = "doorstop"
    DOORSTOP_PUBLISH = "doorstop-publish"
    CORPUS_BUILD = "corpus-build"
    QUALIFICATION_MATRIX = "qualification-matrix"
    SEMANTIC_EXTRACTION_QUALIFICATION = "semantic-extraction-qualification"
    QUALIFICATION_ARCHIVE = "qualification-archive"


@dataclass(frozen=True)
class WorkflowStep:
    family: str
    document: str
    stage: WorkflowStage
    command: tuple[str, ...]
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


@dataclass(frozen=True)
class WorkflowExecutionResult:
    executed_steps: tuple[WorkflowStep, ...]
    blocked_documents: tuple[str, ...]
    blocked_families: tuple[str, ...]

    @property
    def completed(self) -> bool:
        return not self.blocked_documents and not self.blocked_families
