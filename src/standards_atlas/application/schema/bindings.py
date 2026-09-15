"""Executable links from central policies to concrete models, writers and resources.

References are strings to avoid importing adapters or feature modules into the
schema core. Architecture tests resolve them and check coverage, marker defaults,
explicit writer guards and all matching shipped resource versions. A model binding
means SchemaBoundModel checks serialization even for unchecked copies; a dict writer
binding means its function checks the actual envelope with require_current_payload.
This is an inventory, not dynamic dispatch or an assertion that arbitrary JSON is safe.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelBinding:
    family: str
    reference: str


@dataclass(frozen=True)
class MarkerBinding:
    """Central family ownership for class markers guarded at an outer boundary."""

    family: str
    reference: str


@dataclass(frozen=True)
class WriterBinding:
    family: str
    reference: str


@dataclass(frozen=True)
class ResourceBinding:
    family: str
    pattern: str
    discriminator: tuple[str, str] | None = None


SCHEMA_MODEL_BINDINGS: tuple[ModelBinding, ...] = (
    ModelBinding(
        "atlasdata-enrichments",
        "standards_atlas.adapters.atlasdata.knowledge_contract:AtlasDataKnowledge",
    ),
    ModelBinding(
        "atlasdata-knowledge-report",
        "standards_atlas.adapters.atlasdata.knowledge_contract:AtlasDataKnowledgeReport",
    ),
    ModelBinding(
        "cbox-enrichments",
        "standards_atlas.application.model.cbox:CBoxEnrichments",
    ),
    ModelBinding(
        "cbox-report",
        "standards_atlas.application.model.cbox:CBoxReport",
    ),
    ModelBinding(
        "review-source-manifest",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewSourceSpec",
    ),
    ModelBinding(
        "review-profile",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewProfile",
    ),
    ModelBinding(
        "review-package",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewPackage",
    ),
    ModelBinding(
        "review-state",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewState",
    ),
    ModelBinding(
        "review-publication",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewPublication",
    ),
    ModelBinding(
        "review-reference-suite",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewReferenceSuite",
    ),
    ModelBinding(
        "review-candidates",
        "standards_atlas.application.semantic_qualification.review_package.preparation_model:CandidateIndex",
    ),
    ModelBinding(
        "review-selection-proposal",
        "standards_atlas.application.semantic_qualification.review_package.preparation_model:SelectionProposal",
    ),
    ModelBinding(
        "review-archive",
        "standards_atlas.application.semantic_qualification.review_package.archive:ReviewArchiveManifest",
    ),
    ModelBinding(
        "review-workbench-evidence",
        "standards_atlas.application.semantic_qualification.review_package.model:WorkbenchEvidence",
    ),
    ModelBinding(
        "formal-ontology-resource",
        "standards_atlas.application.formal_semantics.ontology_definition:FormalOntologyDefinition",
    ),
    ModelBinding(
        "context-adoption-batch",
        "standards_atlas.application.model.context_adoption:ContextAdoptionBatch",
    ),
    ModelBinding(
        "context-adoption-report",
        "standards_atlas.application.model.context_adoption:ContextAdoptionReport",
    ),
    ModelBinding(
        "knowledge-evidence",
        "standards_atlas.adapters.atlasdata.knowledge_contract:EvidenceBlob",
    ),
    ModelBinding(
        "ontology-resource",
        "standards_atlas.application.semantic_ontology.definition:OntologyDefinition",
    ),
    ModelBinding(
        "qualification-consensus",
        "standards_atlas.application.semantic_qualification.consensus:ConsensusReport",
    ),
    ModelBinding(
        "qualification-matrix-manifest",
        "standards_atlas.application.semantic_qualification.qualification_mat"
        "rix:QualificationMatrixManifest",
    ),
    ModelBinding(
        "qualification-matrix-report",
        "standards_atlas.application.semantic_qualification.qualification_mat"
        "rix:QualificationMatrixReport",
    ),
    ModelBinding(
        "qualification-request-timing",
        "standards_atlas.application.semantic_qualification.performance:RequestTiming",
    ),
    ModelBinding(
        "review-workbench-state",
        "standards_atlas.application.semantic_qualification.review_package.model:WorkbenchState",
    ),
    ModelBinding(
        "semantic-task-resource",
        "standards_atlas.application.semantic_qualification.proposals:SemanticTaskDefinition",
    ),
    ModelBinding(
        "source-structure",
        "standards_atlas.application.model.source_structure:SourceStructure",
    ),
    ModelBinding(
        "standards-manifest",
        "standards_atlas.application.catalog.models:StandardCatalog",
    ),
    ModelBinding(
        "complypack-workspace-manifest",
        "standards_atlas.adapters.complytime.complypack:ComplyPackWorkspaceManifest",
    ),
    ModelBinding(
        "complytime-evaluation-feedback-manifest",
        "standards_atlas.adapters.complytime.evaluation_feedback:EvaluationFeedbackManifest",
    ),
    ModelBinding(
        "governance-bundle-manifest",
        "standards_atlas.adapters.complytime.models:GovernanceBundleManifest",
    ),
    ModelBinding(
        "governance-bundle-traceability",
        "standards_atlas.adapters.complytime.models:GovernanceBundleTraceability",
    ),
    ModelBinding(
        "qualification-archive-receipt",
        "standards_atlas.adapters.evaluation.archive_receipt:QualificationArchiveReceipt",
    ),
    ModelBinding(
        "gemara-control-traceability",
        "standards_atlas.adapters.gemara.control_traceability:GemaraControlTraceabilityManifest",
    ),
    ModelBinding(
        "gemara-traceability",
        "standards_atlas.adapters.gemara.traceability:GemaraTraceabilityManifest",
    ),
    ModelBinding(
        "governance-policy-scaffold",
        "standards_atlas.adapters.governance.policy_scaffold:GovernancePolicyScaffoldManifest",
    ),
    ModelBinding(
        "alignment-result",
        "standards_atlas.application.model.alignment:AlignmentMetadata",
    ),
    ModelBinding(
        "alignment-overrides",
        "standards_atlas.application.model.alignment_review:AlignmentOverrideDocument",
    ),
    ModelBinding(
        "engineering-construction-contract",
        "standards_atlas.application.model.engineering_construction:Engineeri"
        "ngConstructionContract",
    ),
    ModelBinding(
        "formula-transcription",
        "standards_atlas.application.model.formula_transcription:FormulaTranscriptionArtifact",
    ),
    ModelBinding(
        "normalized-document",
        "standards_atlas.application.model.normalized_document:NormalizationMetadata",
    ),
    ModelBinding(
        "normalization-run",
        "standards_atlas.application.model.normalized_document:NormalizationRunMetadata",
    ),
    ModelBinding(
        "reference-candidate-document",
        "standards_atlas.application.model.reference_candidates:ReferenceDetectionMetadata",
    ),
    ModelBinding(
        "normalization-golden-case",
        "standards_atlas.application.qualification.golden_corpus:GoldenCaseManifest",
    ),
    ModelBinding(
        "clause-evaluation-annotation",
        "standards_atlas.application.semantic_qualification.annotations:ClauseEvaluationAnnotation",
    ),
    ModelBinding(
        "evaluation-corpus",
        "standards_atlas.application.semantic_qualification.annotations:EvaluationCorpusManifest",
    ),
    ModelBinding(
        "applicability-detail-hitl-consensus",
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_disagreement:ApplicabilityDetailHitlConsensusReport",
    ),
    ModelBinding(
        "applicability-detail-selection",
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailSelection",
    ),
    ModelBinding(
        "applicability-detail-enrichment-report",
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailEnrichmentReport",
    ),
    ModelBinding(
        "applicability-detail-failure-report",
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailFailureReport",
    ),
    ModelBinding(
        "applicability-policy-evaluation-report",
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_evaluation:ApplicabilityPolicyEvaluationReport",
    ),
    ModelBinding(
        "applicability-policy-run-state",
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_qualification:ApplicabilityPolicyRunState",
    ),
    ModelBinding(
        "applicability-policy-replay-report",
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_replay:ApplicabilityPolicyReplayReport",
    ),
    ModelBinding(
        "applicability-policy-run-report",
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_runner:ApplicabilityPolicyRunReport",
    ),
    ModelBinding(
        "applicability-qualification-report",
        "standards_atlas.application.semantic_qualification.applicability_qualification:App"
        "licabilityQualificationReport",
    ),
    ModelBinding(
        "qualification-coverage",
        "standards_atlas.application.semantic_qualification.qualification_cov"
        "erage:QualificationCoverage",
    ),
    ModelBinding(
        "qualification-run-selection",
        "standards_atlas.application.semantic_qualification.run_selection:Qua"
        "lificationRunSelection",
    ),
    ModelBinding(
        "benchmark-manifest",
        "standards_atlas.application.semantic_qualification.workflow:BenchmarkManifest",
    ),
    ModelBinding(
        "applicability-golden-corpus",
        "standards_atlas.application.semantic_qualification.applicability_cor"
        "pus:ApplicabilityGoldenCorpus",
    ),
    ModelBinding(
        "applicability-prediction-snapshot",
        "standards_atlas.application.semantic_qualification.applicability_har"
        "d_cases:ApplicabilityPredictionSnapshot",
    ),
)

SCHEMA_MARKER_BINDINGS: tuple[MarkerBinding, ...] = (
    MarkerBinding(
        "formal-semantic-projection",
        "standards_atlas.domain.model.formal_semantics:FormalSemanticProjection",
    ),
    MarkerBinding(
        "document-knowledge-proposal",
        "standards_atlas.domain.model.knowledge_proposal:DocumentKnowledgeProposal",
    ),
    MarkerBinding(
        "structural-taxonomy-resource",
        "standards_atlas.application.structure.taxonomy_definition:StructuralTaxonomyDefinition",
    ),
    MarkerBinding(
        "governance-selection-profile",
        "standards_atlas.domain.model.governance_selection:GovernanceSelectionProfile",
    ),
    MarkerBinding(
        "governance-subject-group-profile",
        "standards_atlas.domain.model.governance_subject_groups:GovernanceSubjectGroupProfile",
    ),
    MarkerBinding(
        "normalization-qualification-run-report",
        "standards_atlas.application.qualification.report:QualificationRunReporter",
    ),
    MarkerBinding(
        "workflow-run-report",
        "standards_atlas.application.workflow.report:WorkflowRunReporter",
    ),
)


SCHEMA_WRITER_BINDINGS: tuple[WriterBinding, ...] = (
    WriterBinding(
        "normalization-qualification-run-report",
        "standards_atlas.application.qualification.report:QualificationRunReporter.write",
    ),
    WriterBinding(
        "workflow-run-report",
        "standards_atlas.application.workflow.report:WorkflowRunReporter.write",
    ),
    WriterBinding(
        "cascade-provenance",
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "write_cascade_provenance",
    ),
    WriterBinding(
        "cascade-replay",
        "standards_atlas.application.semantic_qualification.cascade_replay:replay_cascade",
    ),
    WriterBinding(
        "engineering-document",
        "standards_atlas.adapters.filesystem.document_repository:"
        "FileSystemEngineeringDocumentRepository.save",
    ),
    WriterBinding(
        "formal-semantic-projection",
        "standards_atlas.adapters.filesystem.formal_semantic_projection_repository:"
        "FileSystemFormalSemanticProjectionRepository.save",
    ),
    WriterBinding(
        "golden-corpus-proposal",
        "standards_atlas.application.semantic_qualification.consensus:_write_outputs",
    ),
    WriterBinding(
        "document-knowledge-proposal",
        "standards_atlas.adapters.filesystem.knowledge_proposal_repository:"
        "FileSystemDocumentKnowledgeProposalRepository.save",
    ),
    WriterBinding(
        "reviewed-alignment-integrity",
        "standards_atlas.adapters.alignment_review.repository:"
        "AlignmentReviewRepository.save_reviewed",
    ),
)


SCHEMA_RESOURCE_BINDINGS: tuple[ResourceBinding, ...] = (
    ResourceBinding(
        "semantic-task-resource",
        "src/standards_atlas/resources/semantic/tasks/**/task.yaml",
        None,
    ),
    ResourceBinding(
        "ontology-resource",
        "src/standards_atlas/resources/ontologies/**/ontology.yaml",
        None,
    ),
    ResourceBinding(
        "formal-ontology-resource",
        "src/standards_atlas/resources/formal_ontologies/**/ontology.yaml",
        None,
    ),
    ResourceBinding(
        "structural-taxonomy-resource",
        "src/standards_atlas/resources/structure-taxonomies/**/taxonomy.yaml",
        None,
    ),
    ResourceBinding(
        "standards-manifest",
        "manifests/*.yaml",
        ("manifest_type", "standards"),
    ),
    ResourceBinding(
        "qualification-matrix-manifest",
        "manifests/*.yaml",
        ("manifest_type", "qualification_matrix"),
    ),
)
