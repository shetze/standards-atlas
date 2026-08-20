"""CLI composition root for concrete Standards Atlas adapters."""

from pathlib import Path

from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingExtractedDocumentRepository,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.pdf import FormulaVisualExtractor
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
        extracted_documents=DoclingExtractedDocumentRepository(
            artifacts, formula_visuals=FormulaVisualExtractor()
        ),
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


def build_alignment_service(workspace: Path):
    from standards_atlas.adapters.alignment import AlignmentArtifactRepository
    from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
    from standards_atlas.application.services import AlignmentService

    return AlignmentService(
        documents=FileSystemEngineeringDocumentRepository(workspace),
        normalized=NormalizationArtifactRepository(workspace),
        candidates=ReferenceCandidateRepository(workspace),
        results=AlignmentArtifactRepository(workspace),
    )


def build_alignment_review_service(workspace: Path, review_root: Path | None = None):
    from standards_atlas.adapters.alignment import AlignmentArtifactRepository
    from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
    from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
    from standards_atlas.application.services import AlignmentReviewService

    review_root = review_root or _review_root_for_workspace(workspace)
    return AlignmentReviewService(
        documents=FileSystemEngineeringDocumentRepository(workspace),
        normalized=NormalizationArtifactRepository(workspace),
        candidates=ReferenceCandidateRepository(workspace),
        automatic=AlignmentArtifactRepository(workspace),
        review=AlignmentReviewRepository(review_root),
    )


def build_document_selection_service(workspace: Path):
    from standards_atlas.application.services import DocumentSelectionService

    return DocumentSelectionService(FileSystemEngineeringDocumentRepository(workspace))


def build_document_composition_service(workspace: Path):
    from standards_atlas.application.services import DocumentCompositionService

    return DocumentCompositionService(FileSystemEngineeringDocumentRepository(workspace))


def build_reference_candidate_service(workspace: Path):
    from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
    from standards_atlas.application.services import ReferenceCandidateService

    documents = FileSystemEngineeringDocumentRepository(workspace)
    selection = build_document_selection_service(workspace)
    return ReferenceCandidateService(
        documents=documents,
        normalized=NormalizationArtifactRepository(workspace),
        results=ReferenceCandidateRepository(workspace),
        selection=selection,
    )


def build_content_enrichment_service(workspace: Path, review_root: Path | None = None):
    from standards_atlas.adapters.alignment import AlignmentArtifactRepository
    from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
    from standards_atlas.adapters.engineering_construction import (
        EngineeringConstructionContractRepository,
    )
    from standards_atlas.application.services import ContentEnrichmentService

    review_root = review_root or _review_root_for_workspace(workspace)
    return ContentEnrichmentService(
        documents=FileSystemEngineeringDocumentRepository(workspace),
        normalized=NormalizationArtifactRepository(workspace),
        alignments=AlignmentArtifactRepository(workspace),
        reviews=AlignmentReviewRepository(review_root),
        contracts=EngineeringConstructionContractRepository(workspace),
    )


def build_atlasdata_toc_service():
    from standards_atlas.adapters.atlasdata import AtlasDataImporter
    from standards_atlas.adapters.atlasdata.roundtrip_writer import AtlasDataRoundTripWriter
    from standards_atlas.application.services import AtlasDataTocService

    return AtlasDataTocService(AtlasDataImporter(), AtlasDataRoundTripWriter())


def build_golden_corpus_qualifier():
    from standards_atlas.adapters.docling import DoclingJsonReader
    from standards_atlas.application.qualification import GoldenCorpusQualifier

    return GoldenCorpusQualifier(DoclingJsonReader())


def build_clause_reference_extraction_service(workspace: Path):
    from standards_atlas.application.semantic_qualification.references import (
        ClauseReferenceExtractionService,
    )

    return ClauseReferenceExtractionService(FileSystemEngineeringDocumentRepository(workspace))


def _review_root_for_workspace(workspace: Path) -> Path:
    """Derive the project-local HITL root from an engineering-data workspace."""
    resolved = workspace.resolve()
    if resolved.name == "data" and resolved.parent.name == ".atlas":
        project_root = resolved.parent.parent
    elif resolved.name == ".atlas":
        # Compatibility for explicitly supplied legacy/generic test workspaces.
        project_root = resolved.parent
    else:
        project_root = Path.cwd().resolve()
    return project_root / "local" / "review" / "alignment"
