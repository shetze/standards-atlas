"""CLI composition root for concrete Standards Atlas adapters."""

from pathlib import Path

from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingExtractedDocumentRepository,
)
from standards_atlas.adapters.filesystem import (
    FileSystemComposedDocumentViewRepository,
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentReader,
)
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.pdf import FormulaVisualExtractor
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.services import (
    DocumentNormalizationService,
    MarkdownExportService,
)
from standards_atlas.application.services.semantic_classification_service import (
    SemanticClassificationProgressCallback,
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
    documents = FileSystemEngineeringDocumentRepository(workspace)
    views = FileSystemComposedDocumentViewRepository(_work_root_for_workspace(workspace))
    return MarkdownExportService(
        exporter=MarkdownExporter(),
        documents=FileSystemPublicationDocumentReader(documents, views),
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


def build_document_selection_service(
    workspace: Path,
    *,
    source_workspace: Path | None = None,
):
    from standards_atlas.application.services import DocumentSelectionService

    target = FileSystemEngineeringDocumentRepository(workspace)
    source = (
        FileSystemEngineeringDocumentRepository(source_workspace)
        if source_workspace is not None
        else target
    )
    return DocumentSelectionService(source, target)


def build_document_composition_service(workspace: Path):
    from standards_atlas.application.services import DocumentCompositionService

    return DocumentCompositionService(
        FileSystemEngineeringDocumentRepository(workspace),
        FileSystemComposedDocumentViewRepository(_work_root_for_workspace(workspace)),
    )


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


def build_structural_taxonomy_service(workspace: Path):
    from standards_atlas.application.services import StructuralTaxonomyService

    return StructuralTaxonomyService(FileSystemEngineeringDocumentRepository(workspace))


def build_ontology_classification_service(
    workspace: Path,
    *,
    llm_config_path: Path | None = None,
    progress: SemanticClassificationProgressCallback | None = None,
):
    from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
    from standards_atlas.application.ontology import (
        LlmRoleSemanticsClassifier,
        OntologyReference,
        ResourceOntologyDefinitionRepository,
    )
    from standards_atlas.application.semantic_classification import (
        LlmSemanticClassifier,
        SemanticClassificationEngine,
        SemanticClassifierRegistry,
        SemanticProfile,
    )
    from standards_atlas.application.services import SemanticClassificationService

    config = LlmConfig.load(llm_config_path)
    gateway = OpenAICompatibleLlmGateway(config)
    classifier = LlmSemanticClassifier(gateway, model=config.model)
    profile = SemanticProfile(
        id="semantic-profile-2.2.0",
        dimensions={
            "statement_functions": OntologyReference(id="statement-functions", version="2.0.0"),
            "knowledge_kinds": OntologyReference(id="knowledge-kinds", version="2.1.0"),
            "process_functions": OntologyReference(id="process-functions", version="1.0.0"),
            "applicability_functions": OntologyReference(
                id="applicability-functions", version="1.1.0"
            ),
        },
    )
    engine = SemanticClassificationEngine(
        definitions=ResourceOntologyDefinitionRepository(),
        registry=SemanticClassifierRegistry((classifier,)),
    )
    return SemanticClassificationService(
        documents=FileSystemEngineeringDocumentRepository(workspace),
        engine=engine,
        profile=profile,
        role_semantics=LlmRoleSemanticsClassifier(gateway, model=config.model),
        progress=progress,
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


def _work_root_for_workspace(workspace: Path) -> Path:
    """Resolve work storage without assuming callers always use .atlas/data."""
    if workspace.name == "data":
        return workspace.parent / "work"
    return workspace / "work"
