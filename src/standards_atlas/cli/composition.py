"""CLI composition root for concrete Standards Atlas adapters."""

from pathlib import Path

from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingExtractedDocumentRepository,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.services import (
    DocumentNormalizationService,
    MarkdownExportService,
)
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    WorkflowExecutor,
    WorkflowRecovery,
)


def build_document_normalization_service(
    workspace: Path,
) -> DocumentNormalizationService:
    artifacts = DoclingArtifactRepository(workspace)
    return DocumentNormalizationService(
        extracted_documents=DoclingExtractedDocumentRepository(artifacts),
        normalized_documents=NormalizationArtifactRepository(workspace),
    )


def build_markdown_export_service(workspace: Path) -> MarkdownExportService:
    return MarkdownExportService(
        exporter=MarkdownExporter(),
        documents=FileSystemEngineeringDocumentRepository(workspace),
    )


def build_workflow_service(project_root: Path) -> EndToEndWorkflowService:
    recovery = WorkflowRecovery(FileSystemWorkflowArtifactStore())
    return EndToEndWorkflowService(executor=WorkflowExecutor(recovery))
