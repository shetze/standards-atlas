"""Inventory of interfaces whose versions cross architectural lifecycle boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleBoundary(StrEnum):
    """Boundary that makes an interface independently consumable."""

    PERSISTENCE = "persistence"
    PROCESS = "process"
    PACKAGED_RESOURCE = "packaged-resource"
    PUBLIC_CONTRACT = "public-contract"


class VersionAxis(StrEnum):
    """Independent version axes carried by an interface."""

    SCHEMA = "schema"
    RESOURCE = "resource"


@dataclass(frozen=True)
class VersionedInterface:
    """One explicit lifecycle-crossing interface and its versioning obligations."""

    id: str
    location: str
    boundary: LifecycleBoundary
    axes: tuple[VersionAxis, ...]
    schema_family: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError(f"versioned interface {self.id!r} must declare at least one axis")
        if VersionAxis.SCHEMA in self.axes and self.schema_family is None:
            raise ValueError(
                f"versioned interface {self.id!r} declares schema versioning "
                "without a schema family"
            )
        if VersionAxis.SCHEMA not in self.axes and self.schema_family is not None:
            raise ValueError(
                f"versioned interface {self.id!r} has a schema family but no schema version axis"
            )


class SchemaMarkerDisposition(StrEnum):
    """Architectural ownership of an explicit ``schema_version`` marker."""

    CENTRAL = "central"
    LOCAL = "local"


@dataclass(frozen=True)
class SchemaMarkerDecision:
    """Class-level schema marker classification discovered during R5 inventory.

    ``CENTRAL`` entries cross an independent lifecycle boundary and therefore map to
    one ``SchemaPolicy`` family. ``LOCAL`` entries are embedded, diagnostic, legacy,
    or otherwise do not define an independently consumed serialization contract.
    """

    reference: str
    disposition: SchemaMarkerDisposition
    schema_family: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.disposition is SchemaMarkerDisposition.CENTRAL and not self.schema_family:
            raise ValueError(f"central schema marker {self.reference!r} requires a schema family")
        if self.disposition is SchemaMarkerDisposition.LOCAL and self.schema_family is not None:
            raise ValueError(f"local schema marker {self.reference!r} cannot own a schema family")
        if self.disposition is SchemaMarkerDisposition.LOCAL and not self.reason:
            raise ValueError(f"local schema marker {self.reference!r} requires a reason")


@dataclass(frozen=True)
class SchemaEnvelopeDecision:
    """Ownership decision for a function scope constructing schema-versioned mappings."""

    reference: str
    marker_count: int
    disposition: SchemaMarkerDisposition
    schema_families: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.marker_count < 1:
            raise ValueError(f"schema envelope {self.reference!r} needs a positive marker count")
        if self.disposition is SchemaMarkerDisposition.CENTRAL and not self.schema_families:
            raise ValueError(f"central schema envelope {self.reference!r} requires a family")
        if self.disposition is SchemaMarkerDisposition.LOCAL and self.schema_families:
            raise ValueError(f"local schema envelope {self.reference!r} cannot own schema families")
        if self.disposition is SchemaMarkerDisposition.LOCAL and not self.reason:
            raise ValueError(f"local schema envelope {self.reference!r} requires a reason")


SCHEMA_ENVELOPE_MARKER_COUNTS: tuple[tuple[str, int], ...] = (
    (
        "standards_atlas.adapters.alignment_review.repository:AlignmentReview"
        "Repository.save_reviewed",
        1,
    ),
    (
        "standards_atlas.adapters.docling.converter:DoclingPdfConverter.conversion_metadata",
        1,
    ),
    (
        "standards_atlas.adapters.filesystem.document_repository:FileSystemEn"
        "gineeringDocumentRepository.save",
        1,
    ),
    (
        "standards_atlas.adapters.filesystem.formal_semantic_projection_repos"
        "itory:FileSystemFormalSemanticProjectionRepository.save",
        1,
    ),
    (
        "standards_atlas.adapters.filesystem.semantic_extraction_repository:F"
        "ileSystemSemanticExtractionRepository.save",
        1,
    ),
    (
        "standards_atlas.adapters.normalization.repository:NormalizationArtifactRepository.save",
        1,
    ),
    (
        "standards_atlas.adapters.workflow.artifact_store:FileSystemWorkflowA"
        "rtifactStore.record_completion",
        2,
    ),
    (
        "standards_atlas.adapters.workflow.artifact_store:_write_fresh_repetition_marker",
        1,
    ),
    (
        "standards_atlas.adapters.workflow.baseline_archive:archive_enrichment_baseline",
        2,
    ),
    (
        "standards_atlas.application.evaluation.report:EvaluationReporter.write_matrix_summary",
        1,
    ),
    (
        "standards_atlas.application.normalization_quality.report:Normalizati"
        "onQualityReporter.write",
        1,
    ),
    (
        "standards_atlas.application.qualification.report:QualificationRunReporter.write",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.analysis_archive:_build_run_metadata",
        2,
    ),
    (
        "standards_atlas.application.semantic_qualification.analysis_archive:_update_run_index",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "build_analysis_metrics",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "create_analysis_archive",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "write_cascade_provenance",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.campaign_activation:activate_campaign",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.campaign_evaluation:evaluate_campaign",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.campaign_executio"
        "n:FreshLedgerGateway.generate_structured",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.campaign_execution:run_campaign",
        2,
    ),
    (
        "standards_atlas.application.semantic_qualification.campaign_selection:prepare_campaign",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.cascade_replay:replay_cascade",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.challenger:load_hard_case_selection",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.challenger:write_challenger_comparison",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.consensus:_write_outputs",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.focused_resolutio"
        "n:plan_focused_resolution",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_audit:audit_partial_experiment",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_cascade:_write_report",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_cascade:run_partial_cascade",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_cascade:w"
        "rite_partial_cascade_costs",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_cascade_a"
        "udit:audit_partial_cascade",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_compariso"
        "n:compare_efficient_prompts",
        2,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_compariso"
        "n:compare_partial_profiles",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.partial_proposals"
        ":run_partial_proposals",
        2,
    ),
    (
        "standards_atlas.application.semantic_qualification.proposals:Baselin"
        "eProposalGenerator.run.process_example",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.review_package.pu"
        "blication:compile_publication",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.review_package.pu"
        "blication:publication_suites",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.semantic_readines"
        "s:evaluate_semantic_readiness",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.taxonomy_diagnost"
        "ics:diagnose_taxonomy_decisions",
        2,
    ),
    (
        "standards_atlas.application.semantic_qualification.taxonomy_pilot:build_taxonomy_pilot",
        1,
    ),
    (
        "standards_atlas.application.semantic_qualification.taxonomy_pilot:synthetic_pilot",
        1,
    ),
    (
        "standards_atlas.application.services.context_run_report:write_context_run_report",
        1,
    ),
    (
        "standards_atlas.application.workflow.report:WorkflowRunReporter.write",
        1,
    ),
    (
        "standards_atlas.cli.commands.evaluation_commands.qualification_archi"
        "ve:finalize_qualification_archive",
        1,
    ),
)

SCHEMA_ENVELOPE_DECISIONS: tuple[SchemaEnvelopeDecision, ...] = (
    SchemaEnvelopeDecision(
        "standards_atlas.adapters.docling.converter:DoclingPdfConverter.conversion_metadata",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("docling-conversion-metadata",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.adapters.normalization.repository:NormalizationArtifactRepository.save",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("method-technique-index",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.adapters.workflow.artifact_store:FileSystemWorkflowA"
        "rtifactStore.record_completion",
        2,
        SchemaMarkerDisposition.CENTRAL,
        ("workflow-input-marker", "workflow-step-marker"),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.adapters.workflow.artifact_store:_write_fresh_repetition_marker",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("workflow-fresh-repetition-marker",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.adapters.workflow.baseline_archive:archive_enrichment_baseline",
        2,
        SchemaMarkerDisposition.CENTRAL,
        ("enrichment-baseline", "enrichment-baseline-manifest"),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.evaluation.report:EvaluationReporter.write_matrix_summary",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("evaluation-matrix-summary",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.normalization_quality.report:Normalizati"
        "onQualityReporter.write",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("normalization-quality-report",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.analysis_archive:_build_run_metadata",
        2,
        SchemaMarkerDisposition.CENTRAL,
        ("qualification-run-metadata",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.analysis_archive:_update_run_index",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("qualification-run-index",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "build_analysis_metrics",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("qualification-analysis-metrics",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.analysis_archive:"
        "create_analysis_archive",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("qualification-analysis-archive-manifest",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.campaign_selection:prepare_campaign",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("partial-qualification-campaign",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.challenger:load_hard_case_selection",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("challenger-sample-selection",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.challenger:write_challenger_comparison",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("challenger-comparison",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.focused_resolutio"
        "n:plan_focused_resolution",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("focused-resolution-plan",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.partial_audit:audit_partial_experiment",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("partial-experiment-audit",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.partial_cascade:w"
        "rite_partial_cascade_costs",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("partial-cascade-costs",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.partial_compariso"
        "n:compare_efficient_prompts",
        2,
        SchemaMarkerDisposition.CENTRAL,
        ("efficient-comparison-plan", "efficient-prompt-comparison"),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.partial_compariso"
        "n:compare_partial_profiles",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("partial-profile-comparison",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.proposals:Baselin"
        "eProposalGenerator.run.process_example",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("semantic-evaluation",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.taxonomy_pilot:synthetic_pilot",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("semantic-readiness-checks",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.services.context_run_report:write_context_run_report",
        1,
        SchemaMarkerDisposition.CENTRAL,
        ("context-run-report",),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.review_package.pu"
        "blication:compile_publication",
        1,
        SchemaMarkerDisposition.LOCAL,
        reason=(
            "temporary constructor mapping is immediately sealed into the central"
            "ly versioned ReviewPublication model"
        ),
    ),
    SchemaEnvelopeDecision(
        "standards_atlas.application.semantic_qualification.review_package.pu"
        "blication:publication_suites",
        1,
        SchemaMarkerDisposition.LOCAL,
        reason=(
            "temporary constructor mapping is immediately validated as the centra"
            "lly versioned SemanticReferenceSuite model"
        ),
    ),
)

SCHEMA_MARKER_DECISIONS: tuple[SchemaMarkerDecision, ...] = (
    SchemaMarkerDecision(
        "standards_atlas.adapters.atlasdata.semantic_annotation_writer:Public"
        "SemanticAnnotationManifest",
        SchemaMarkerDisposition.CENTRAL,
        "public-semantic-annotation-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.complytime.complypack:ComplyPackWorkspaceManifest",
        SchemaMarkerDisposition.CENTRAL,
        "complypack-workspace-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.complytime.evaluation_feedback:EvaluationFeedbackManifest",
        SchemaMarkerDisposition.CENTRAL,
        "complytime-evaluation-feedback-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.complytime.models:GovernanceBundleManifest",
        SchemaMarkerDisposition.CENTRAL,
        "governance-bundle-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.complytime.models:GovernanceBundleTraceability",
        SchemaMarkerDisposition.CENTRAL,
        "governance-bundle-traceability",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.evaluation.archive_receipt:QualificationArchiveReceipt",
        SchemaMarkerDisposition.CENTRAL,
        "qualification-archive-receipt",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.gemara.control_traceability:GemaraControlTraceabilityManifest",
        SchemaMarkerDisposition.CENTRAL,
        "gemara-control-traceability",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.gemara.traceability:GemaraTraceabilityManifest",
        SchemaMarkerDisposition.CENTRAL,
        "gemara-traceability",
    ),
    SchemaMarkerDecision(
        "standards_atlas.adapters.governance.policy_scaffold:GovernancePolicyScaffoldManifest",
        SchemaMarkerDisposition.CENTRAL,
        "governance-policy-scaffold",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.context.subject_identification:SubjectIdentificationReport",
        SchemaMarkerDisposition.LOCAL,
        reason="runtime deterministic analysis result; no independent reader",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.context.subject_vocabulary:SubjectCandidateVocabulary",
        SchemaMarkerDisposition.LOCAL,
        reason="optional diagnostic export; no independent reader contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.alignment:AlignmentMetadata",
        SchemaMarkerDisposition.CENTRAL,
        "alignment-result",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.alignment_review:AlignmentOverrideDocument",
        SchemaMarkerDisposition.CENTRAL,
        "alignment-overrides",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.alignment_review:ReviewMetadata",
        SchemaMarkerDisposition.LOCAL,
        reason="embedded review metadata with no independent persistence boundary",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.engineering_construction:Engineeri"
        "ngConstructionContract",
        SchemaMarkerDisposition.CENTRAL,
        "engineering-construction-contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.formula_transcription:FormulaTranscriptionArtifact",
        SchemaMarkerDisposition.CENTRAL,
        "formula-transcription",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.normalized_document:TransformationLedger",
        SchemaMarkerDisposition.LOCAL,
        reason="embedded in normalized-document payload and owned by that contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.normalized_document:NormalizationMetadata",
        SchemaMarkerDisposition.CENTRAL,
        "normalized-document",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.normalized_document:NormalizationRunMetadata",
        SchemaMarkerDisposition.CENTRAL,
        "normalization-run",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.model.reference_candidates:ReferenceDetectionMetadata",
        SchemaMarkerDisposition.CENTRAL,
        "reference-candidate-document",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.qualification.golden_corpus:GoldenCaseManifest",
        SchemaMarkerDisposition.CENTRAL,
        "normalization-golden-case",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.qualification.golden_corpus:GoldenCorpusReport",
        SchemaMarkerDisposition.LOCAL,
        reason=("in-memory qualification result; persisted envelope is owned by run reporter"),
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.qualification.report:QualificationRunReporter",
        SchemaMarkerDisposition.CENTRAL,
        "normalization-qualification-run-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.acceptance_profil"
        "es:PartialAcceptanceProfile",
        SchemaMarkerDisposition.CENTRAL,
        "partial-acceptance-profile",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.annotations:ClauseEvaluationAnnotation",
        SchemaMarkerDisposition.CENTRAL,
        "clause-evaluation-annotation",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.annotations:EvaluationCorpusManifest",
        SchemaMarkerDisposition.CENTRAL,
        "evaluation-corpus",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_cor"
        "pus:ApplicabilityGoldenCorpus",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-golden-corpus",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_cor"
        "pus:_LegacyApplicabilityGoldenCorpus",
        SchemaMarkerDisposition.LOCAL,
        reason="explicit legacy parser implementation detail",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_cor"
        "pus:ApplicabilityDetailGoldenSeed",
        SchemaMarkerDisposition.LOCAL,
        reason=("local golden-seed review artifact with no independent reader contract"),
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_cor"
        "pus:ApplicabilityGoldenRegressionReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local evaluation report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_comparison:ApplicabilityDetailComparisonReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local evaluation report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_disagreement:ApplicabilityDetailHitlConsensusReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-detail-hitl-consensus",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_disagreement:ApplicabilityDetailHitlEvaluationReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local evaluation report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailSelection",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-detail-selection",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailEnrichmentReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-detail-enrichment-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_enrichment:ApplicabilityDetailFailureReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-detail-failure-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_det"
        "ail_model_matrix:ApplicabilityDetailModelMatrixReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local model-comparison report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_end"
        "_to_end:ApplicabilityEndToEndRegressionReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local regression report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_fra"
        "ming:ApplicabilityFramingReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local framing diagnostic report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_har"
        "d_cases:ApplicabilityPredictionSnapshot",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-prediction-snapshot",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_har"
        "d_cases:PresenceHardCaseReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local hard-case analysis report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_archive:ApplicabilityPolicyArchiveSummary",
        SchemaMarkerDisposition.LOCAL,
        reason="archive summary embedded in a larger qualification archive contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_evaluation:ApplicabilityPolicyEvaluationReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-policy-evaluation-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_qualification:ApplicabilityPolicyRunState",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-policy-run-state",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_replay:ApplicabilityPolicyReplayReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-policy-replay-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.applicability_pol"
        "icy_runner:ApplicabilityPolicyRunReport",
        SchemaMarkerDisposition.CENTRAL,
        "applicability-policy-run-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.prompt_comparison"
        ":PromptComparisonReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local prompt-comparison report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.qualification:Ann"
        "otationQualificationReport",
        SchemaMarkerDisposition.CENTRAL,
        "annotation-qualification-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.qualification_cov"
        "erage:QualificationCoverage",
        SchemaMarkerDisposition.CENTRAL,
        "qualification-coverage",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.references:ClauseReferenceAnalysis",
        SchemaMarkerDisposition.LOCAL,
        reason="task-local structured model output owned by its task contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.review:ReviewForm",
        SchemaMarkerDisposition.CENTRAL,
        "annotation-review-form",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.role_corpus:RoleCorpusBuildManifest",
        SchemaMarkerDisposition.CENTRAL,
        "role-corpus-build-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.role_corpus:RoleGoldenCorpus",
        SchemaMarkerDisposition.CENTRAL,
        "role-golden-corpus",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.run_selection:Qua"
        "lificationRunSelection",
        SchemaMarkerDisposition.CENTRAL,
        "qualification-run-selection",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.semantic_extracti"
        "on_qualification:SemanticExtractionQualificationReport",
        SchemaMarkerDisposition.LOCAL,
        reason="local qualification report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.semantic_qualification.workflow:BenchmarkManifest",
        SchemaMarkerDisposition.CENTRAL,
        "benchmark-manifest",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.structure.taxonomy_definition:StructuralTaxonomyDefinition",
        SchemaMarkerDisposition.CENTRAL,
        "structural-taxonomy-resource",
    ),
    SchemaMarkerDecision(
        "standards_atlas.application.workflow.report:WorkflowRunReporter",
        SchemaMarkerDisposition.CENTRAL,
        "workflow-run-report",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.artifact_lineage:ArtifactLineage",
        SchemaMarkerDisposition.LOCAL,
        reason="embedded provenance record owned by its containing artifact schema",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.formal_semantics:FormalSemanticProjection",
        SchemaMarkerDisposition.CENTRAL,
        "formal-semantic-projection",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.governance_selection:GovernanceSelectionProfile",
        SchemaMarkerDisposition.CENTRAL,
        "governance-selection-profile",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.governance_selection:GovernanceCandidateAnalysis",
        SchemaMarkerDisposition.LOCAL,
        reason="local review/export analysis; no independent reader contract",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.governance_subject_groups:GovernanceSubjectGroupProfile",
        SchemaMarkerDisposition.CENTRAL,
        "governance-subject-group-profile",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.reference_mention:ReferenceMention",
        SchemaMarkerDisposition.LOCAL,
        reason="embedded in canonical EngineeringDocument clauses",
    ),
    SchemaMarkerDecision(
        "standards_atlas.domain.model.semantic_extraction:DocumentSemanticExtraction",
        SchemaMarkerDisposition.CENTRAL,
        "semantic-extraction",
    ),
)

VERSIONED_INTERFACES: tuple[VersionedInterface, ...] = (
    VersionedInterface(
        "partial-review-workbench-evidence",
        "**/review-evidence.json#workbench",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-workbench-evidence",
    ),
    VersionedInterface(
        "partial-review-archive",
        "**/review-package.zip#archive-manifest.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-archive",
    ),
    VersionedInterface(
        "partial-review-handoff",
        "**/review-handoff.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-handoff",
    ),
    VersionedInterface(
        "review-workbench-state",
        "**/workbench/state.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "review-workbench-state",
        notes="Navigation and Holdout exposure, never semantic confirmation authority.",
    ),
    VersionedInterface(
        "partial-review-candidates",
        "**/preparation/indexes/*/index.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-candidates",
    ),
    VersionedInterface(
        "partial-review-selection-proposal",
        "**/preparation/selections/*/selection.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-selection-proposal",
    ),
    VersionedInterface(
        "partial-review-package",
        "**/review-package.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-package",
    ),
    VersionedInterface(
        "partial-review-state",
        "**/review-state.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-state",
    ),
    VersionedInterface(
        "partial-review-profile",
        "**/review-profile.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-profile",
    ),
    VersionedInterface(
        "partial-review-publication",
        "**/review-evidence.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-review-publication",
    ),
    VersionedInterface(
        "partial-qualification-manifest",
        "**/campaign.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualification-manifest",
        notes=(
            "Current-only manifest 1.1; campaign artifact 2.0 declares review evidence separately."
        ),
    ),
    VersionedInterface(
        "partial-qualification-campaign",
        "**/campaign-plan.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualification-campaign",
        notes="Current-only 2.0: external_suites, atlas_publication or archived_handoff.",
    ),
    VersionedInterface(
        "partial-qualification-repeat",
        "**/repeat.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualification-repeat",
    ),
    VersionedInterface(
        "partial-qualification-evaluation",
        "**/qualification-evaluation.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualification-evaluation",
    ),
    VersionedInterface(
        "partial-semantic-reference",
        "**/semantic-reference.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-semantic-reference",
    ),
    VersionedInterface(
        "partial-qualified-activation",
        "**/activation.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualified-activation",
    ),
    VersionedInterface(
        "qualification-request-event",
        "**/qualification-events/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-request-event",
    ),
    VersionedInterface(
        "partial-qualification-execution",
        "**/execution-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-qualification-execution",
    ),
    VersionedInterface(
        "partial-cascade-report",
        "**/partial-cascade-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-cascade-report",
        "Effective prompt and explicit planned/unmeasured versus executed diagnostics.",
    ),
    VersionedInterface(
        "partial-cascade-audit",
        "**/partial-cascade-audit.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-cascade-audit",
        "Immutable acceptance replay, blockers and physical attempt diagnostics.",
    ),
    VersionedInterface(
        "taxonomy-pilot-readiness",
        "**/pilot-readiness.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "taxonomy-pilot-readiness",
        "Source-bound or explicit synthetic readiness; not implicit rule approval.",
    ),
    VersionedInterface(
        "taxonomy-readiness-cases",
        "resources/semantic/qualification/taxonomy-readiness-v1/cases.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA,),
        "taxonomy-readiness-cases",
        "Synthetic source authority and independent process/plan smoke expectations.",
    ),
    VersionedInterface(
        "semantic-readiness-checks",
        "**/readiness-checks.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "semantic-readiness-checks",
        "Source identity and minimum process/plan sentinel expectations.",
    ),
    VersionedInterface(
        "semantic-readiness-evaluation",
        "**/semantic-readiness.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "semantic-readiness-evaluation",
        "Scoped sentinel comparison; never domain qualification or canonical acceptance.",
    ),
    VersionedInterface(
        "mixed-consensus",
        "**/mixed-consensus-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "mixed-consensus",
        "Attribute-specific acceptance without synthetic votes or semantic defaults.",
    ),
    VersionedInterface(
        "partial-cascade-run",
        "**/partial-cascade-*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-cascade-run",
        "Frozen completion profile, source inputs and staged sparse evidence.",
    ),
    VersionedInterface(
        "partial-request-plan",
        "**/partial-request-plan.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-request-plan",
        "Experimental source-bound question plan; no synthetic model votes.",
    ),
    VersionedInterface(
        "partial-semantic-observation",
        "**/partial-observation.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-semantic-observation",
        "Explicit evaluated, not_requested and failed attributes; sparse evidence only.",
    ),
    VersionedInterface(
        "partial-proposal-run",
        "**/partial-run-*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-proposal-run",
        "Immutable experiment identity and measured execution report.",
    ),
    VersionedInterface(
        "source-structure",
        "clause-descriptor.source_structure",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "source-structure",
    ),
    VersionedInterface(
        "clause-decision-plan",
        "**/taxonomy-decision-plans.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "clause-decision-plan",
    ),
    VersionedInterface(
        "taxonomy-decision-report",
        "**/taxonomy-decision-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "taxonomy-decision-report",
    ),
    VersionedInterface(
        "taxonomy-decision-rules",
        "resources/semantic/taxonomy-decisions/**/rules.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "taxonomy-decision-rules",
    ),
    VersionedInterface(
        "taxonomy-decision-review",
        "resources/semantic/taxonomy-decisions/**/review.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "taxonomy-decision-review",
    ),
    VersionedInterface(
        "cascade-provenance",
        "**/cascade-provenance.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "cascade-provenance",
        "Explicit missing consensus outcomes and canonical role_relation counters.",
    ),
    VersionedInterface(
        "cascade-replay",
        "**/cascade-replay.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "cascade-replay",
        "Offline historical, routing and verified-proposal audit; no model calls.",
    ),
    VersionedInterface(
        "qualification-request-timing",
        "**/request-timing.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-request-timing",
        "Measured call wall times; fresh and cached provider durations remain separate.",
    ),
    VersionedInterface(
        "qualification-matrix-report",
        "**/qualification-matrix.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-matrix-report",
        "Per-request performance denominator, totals and timing coverage.",
    ),
    VersionedInterface(
        "qualification-consensus",
        "**/consensus-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-consensus",
        "Current-only measured process primary/set; no legacy fingerprint serializer.",
    ),
    VersionedInterface(
        "golden-corpus-proposal",
        "**/golden-corpus-proposal.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "golden-corpus-proposal",
        "Review proposal including explicit process availability and support.",
    ),
    VersionedInterface(
        "cbox-enrichments",
        "clause-descriptor.enrichment_context",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "cbox-enrichments",
        "Read-only canonical attribute projection.",
    ),
    VersionedInterface(
        "cbox-report",
        "local/**/cbox*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "cbox-report",
        "Local effective post-import CBox and provenance.",
    ),
    VersionedInterface(
        "atlasdata-enrichments",
        "data/enrichments/*.yaml",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "atlasdata-enrichments",
        "Selected generated/confirmed attributes; protected values are hash references.",
    ),
    VersionedInterface(
        "knowledge-evidence",
        ".atlas/data/knowledge-evidence/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-evidence",
        "Private immutable hydration payloads.",
    ),
    VersionedInterface(
        "atlasdata-knowledge-report",
        "local/**/atlasdata-knowledge*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "atlasdata-knowledge-report",
        "Explicit export/import preflight reports.",
    ),
    VersionedInterface(
        "knowledge-adoption-batch",
        "local/**/knowledge-adoption-batch.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-adoption-batch",
        "Optional serialized partial-update contract; omitted fields remain unaddressed.",
    ),
    VersionedInterface(
        "knowledge-adoption-report",
        "local/**/knowledge-adoption-report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "knowledge-adoption-report",
        "Explicit canonical adoption preview/write report, not public AtlasData.",
    ),
    VersionedInterface(
        "engineering-document",
        ".atlas/data/documents/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "engineering-document",
        "Canonical persisted knowledge state for one physical document.",
    ),
    VersionedInterface(
        "standards-manifest",
        "manifests/standards*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "standards-manifest",
        "Authored workflow/catalog input consumed independently of Python code.",
    ),
    VersionedInterface(
        "qualification-matrix-manifest",
        "manifests/*qualification*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "qualification-matrix-manifest",
        "Authored qualification execution contract.",
    ),
    VersionedInterface(
        "semantic-task",
        "resources/semantic/tasks/<id>/<version>/task.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "semantic-task-resource",
        "Task resource version identifies inference semantics independently of YAML schema.",
    ),
    VersionedInterface(
        "semantic-profile",
        "resources/semantic/profiles/<id>/<version>/profile.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "semantic-profile-resource",
        "Profile version identifies a domain composition independently of YAML schema.",
    ),
    VersionedInterface(
        "semantic-ontology",
        "resources/ontologies/<id>/<version>/ontology.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "ontology-resource",
        "Vocabulary/resource version identifies controlled meaning independently of YAML schema.",
    ),
    VersionedInterface(
        "structural-taxonomy",
        "resources/structure-taxonomies/<id>/<version>/taxonomy.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "structural-taxonomy-resource",
        "Taxonomy definition version evolves independently of its serialization schema.",
    ),
    VersionedInterface(
        "formal-ontology",
        "resources/formal_ontologies/<id>/<version>/ontology.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA, VersionAxis.RESOURCE),
        "formal-ontology-resource",
        "OWL/TBox resource identity is independent of the ontology-definition schema.",
    ),
    VersionedInterface(
        "semantic-prompt",
        "resources/semantic/prompts/<task>/<version>/",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.RESOURCE,),
        notes=(
            "Prompt versions are independently selectable inference inputs; "
            "their output schema is task-owned."
        ),
    ),
    VersionedInterface(
        "formal-semantic-projection",
        ".atlas/data/formal-semantic-projections/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "formal-semantic-projection",
        "Persisted projection records referenced ontology/resource identity separately.",
    ),
    VersionedInterface(
        "semantic-extraction",
        ".atlas/data/semantic-extractions/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "semantic-extraction",
        (
            "Persisted extraction carries task/prompt/model provenance independently "
            "of schema version."
        ),
    ),
    VersionedInterface(
        "public-semantic-annotation-manifest",
        "local/**/semantic-annotations*.yaml",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "public-semantic-annotation-manifest",
    ),
    VersionedInterface(
        "complypack-workspace-manifest",
        "local/exports/complypack/**/workspace-manifest.yaml",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "complypack-workspace-manifest",
    ),
    VersionedInterface(
        "complytime-evaluation-feedback-manifest",
        "local/**/evaluation-feedback*.json",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "complytime-evaluation-feedback-manifest",
    ),
    VersionedInterface(
        "governance-bundle-manifest",
        "local/exports/complypack/**/governance/manifest.yaml",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "governance-bundle-manifest",
    ),
    VersionedInterface(
        "governance-bundle-traceability",
        "local/exports/complypack/**/governance/traceability.json",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "governance-bundle-traceability",
    ),
    VersionedInterface(
        "qualification-archive-receipt",
        "**/qualification-archive-receipt.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-archive-receipt",
    ),
    VersionedInterface(
        "gemara-control-traceability",
        "**/*.traceability.json#control",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "gemara-control-traceability",
    ),
    VersionedInterface(
        "gemara-traceability",
        "**/*.traceability.json#guidance",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "gemara-traceability",
    ),
    VersionedInterface(
        "governance-policy-scaffold",
        "local/review/governance/**/*.scaffold.json",
        LifecycleBoundary.PUBLIC_CONTRACT,
        (VersionAxis.SCHEMA,),
        "governance-policy-scaffold",
    ),
    VersionedInterface(
        "alignment-result",
        ".atlas/data/alignments/*/alignment.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "alignment-result",
    ),
    VersionedInterface(
        "alignment-overrides",
        "local/review/alignment/*/overrides.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "alignment-overrides",
    ),
    VersionedInterface(
        "engineering-construction-contract",
        ".atlas/data/construction/*/contract.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "engineering-construction-contract",
    ),
    VersionedInterface(
        "formula-transcription",
        ".atlas/data/enrichments/formula-transcriptions/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "formula-transcription",
    ),
    VersionedInterface(
        "normalized-document",
        ".atlas/data/normalized/*/document.json#metadata",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "normalized-document",
    ),
    VersionedInterface(
        "normalization-run",
        ".atlas/data/normalized/*/run.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "normalization-run",
    ),
    VersionedInterface(
        "reference-candidate-document",
        ".atlas/data/reference-candidates/*/document.json#metadata",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "reference-candidate-document",
    ),
    VersionedInterface(
        "normalization-golden-case",
        "tests/golden_corpus/cases/*/manifest.json",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "normalization-golden-case",
    ),
    VersionedInterface(
        "normalization-qualification-run-report",
        ".atlas/data/qualification/runs/*/report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "normalization-qualification-run-report",
    ),
    VersionedInterface(
        "partial-acceptance-profile",
        "cfg/evaluation/partial-cascade/*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "partial-acceptance-profile",
    ),
    VersionedInterface(
        "clause-evaluation-annotation",
        "**/annotations/**/*.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "clause-evaluation-annotation",
    ),
    VersionedInterface(
        "evaluation-corpus",
        "**/corpus.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "evaluation-corpus",
    ),
    VersionedInterface(
        "applicability-detail-hitl-consensus",
        "local/**/applicability-detail-hitl-consensus*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-detail-hitl-consensus",
    ),
    VersionedInterface(
        "applicability-detail-selection",
        "**/applicability-detail-selection*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-detail-selection",
    ),
    VersionedInterface(
        "applicability-detail-enrichment-report",
        "**/applicability-detail-enrichment*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-detail-enrichment-report",
    ),
    VersionedInterface(
        "applicability-detail-failure-report",
        "**/applicability-detail-failures*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-detail-failure-report",
    ),
    VersionedInterface(
        "applicability-policy-evaluation-report",
        "**/applicability-policy-evaluation*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-policy-evaluation-report",
    ),
    VersionedInterface(
        "applicability-policy-run-state",
        "**/applicability-policy-state*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-policy-run-state",
    ),
    VersionedInterface(
        "applicability-policy-replay-report",
        "**/applicability-policy-replay*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-policy-replay-report",
    ),
    VersionedInterface(
        "applicability-policy-run-report",
        "**/applicability-policy-run*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-policy-run-report",
    ),
    VersionedInterface(
        "annotation-qualification-report",
        "**/annotation-qualification*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "annotation-qualification-report",
    ),
    VersionedInterface(
        "qualification-coverage",
        "**/qualification-coverage.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-coverage",
    ),
    VersionedInterface(
        "annotation-review-form",
        "**/review.md#semantic-review",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "annotation-review-form",
    ),
    VersionedInterface(
        "role-corpus-build-manifest",
        "**/role-corpus*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "role-corpus-build-manifest",
    ),
    VersionedInterface(
        "role-golden-corpus",
        "**/role-golden-corpus*.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "role-golden-corpus",
    ),
    VersionedInterface(
        "qualification-run-selection",
        "**/selection.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-run-selection",
    ),
    VersionedInterface(
        "benchmark-manifest",
        "**/benchmark*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "benchmark-manifest",
    ),
    VersionedInterface(
        "governance-selection-profile",
        "local/governance/*.yaml",
        LifecycleBoundary.PROCESS,
        (VersionAxis.SCHEMA,),
        "governance-selection-profile",
    ),
    VersionedInterface(
        "governance-subject-group-profile",
        "resources/governance/subject-groups/**/profile.yaml",
        LifecycleBoundary.PACKAGED_RESOURCE,
        (VersionAxis.SCHEMA,),
        "governance-subject-group-profile",
    ),
    VersionedInterface(
        "workflow-run-report",
        ".atlas/work/workflow/**/report.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "workflow-run-report",
    ),
    VersionedInterface(
        "reviewed-alignment-integrity",
        "local/review/alignment/*/reviewed.integrity.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "reviewed-alignment-integrity",
        "Integrity sidecar is read independently when reviewed alignment is verified.",
    ),
    VersionedInterface(
        "docling-conversion-metadata",
        ".atlas/data/docling/*/conversion.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "docling-conversion-metadata",
    ),
    VersionedInterface(
        "method-technique-index",
        ".atlas/data/normalized/*/methods-and-techniques.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "method-technique-index",
    ),
    VersionedInterface(
        "workflow-input-marker",
        ".atlas/work/workflow/input-state/*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "workflow-input-marker",
    ),
    VersionedInterface(
        "workflow-step-marker",
        ".atlas/work/workflow/**/*.json#step-fingerprint",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "workflow-step-marker",
    ),
    VersionedInterface(
        "workflow-fresh-repetition-marker",
        ".atlas/work/workflow/fresh-repetitions/*",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "workflow-fresh-repetition-marker",
    ),
    VersionedInterface(
        "enrichment-baseline",
        ".atlas/data/evaluation/baselines/enrichments/**/*.zip#baseline.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "enrichment-baseline",
    ),
    VersionedInterface(
        "enrichment-baseline-manifest",
        ".atlas/data/evaluation/baselines/enrichments/**/*.zip#manifest.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "enrichment-baseline-manifest",
    ),
    VersionedInterface(
        "evaluation-matrix-summary",
        "local/evaluation/**/matrix-summary*.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "evaluation-matrix-summary",
    ),
    VersionedInterface(
        "normalization-quality-report",
        "local/evaluation/**/qualification.json#normalization-quality",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "normalization-quality-report",
    ),
    VersionedInterface(
        "qualification-analysis-metrics",
        "**/qualification-analysis-metrics.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-analysis-metrics",
    ),
    VersionedInterface(
        "qualification-analysis-archive-manifest",
        "**/qualification-run-*.zip#archive-manifest.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-analysis-archive-manifest",
    ),
    VersionedInterface(
        "qualification-run-metadata",
        "**/qualification-run-*.zip#qualification-run-metadata.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-run-metadata",
    ),
    VersionedInterface(
        "qualification-run-index",
        "local/evaluation/qualification-run-index.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "qualification-run-index",
    ),
    VersionedInterface(
        "challenger-sample-selection",
        "**/challenger-sample-selection.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "challenger-sample-selection",
    ),
    VersionedInterface(
        "challenger-comparison",
        "**/challenger-comparison.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "challenger-comparison",
    ),
    VersionedInterface(
        "focused-resolution-plan",
        "**/focused-plan.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "focused-resolution-plan",
    ),
    VersionedInterface(
        "partial-experiment-audit",
        "**/partial-audit.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-experiment-audit",
    ),
    VersionedInterface(
        "partial-cascade-costs",
        "**/partial-cascade-costs.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-cascade-costs",
    ),
    VersionedInterface(
        "partial-profile-comparison",
        "**/partial-profile-comparison.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "partial-profile-comparison",
    ),
    VersionedInterface(
        "efficient-comparison-plan",
        "**/efficient-comparison-plan.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "efficient-comparison-plan",
    ),
    VersionedInterface(
        "efficient-prompt-comparison",
        "**/efficient-comparison.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "efficient-prompt-comparison",
    ),
    VersionedInterface(
        "semantic-evaluation",
        "**/evaluation.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "semantic-evaluation",
    ),
    VersionedInterface(
        "context-run-report",
        ".atlas/data/evaluation/context-routing/*-run.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "context-run-report",
    ),
    VersionedInterface(
        "applicability-golden-corpus",
        "local/review/applicability/**/applicability-golden-corpus.yaml",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-golden-corpus",
    ),
    VersionedInterface(
        "applicability-prediction-snapshot",
        "**/applicability-predictions.json",
        LifecycleBoundary.PERSISTENCE,
        (VersionAxis.SCHEMA,),
        "applicability-prediction-snapshot",
    ),
)


def schema_managed_interfaces() -> tuple[VersionedInterface, ...]:
    """Return interfaces whose serialization contract is centrally schema-managed."""

    return tuple(item for item in VERSIONED_INTERFACES if VersionAxis.SCHEMA in item.axes)
