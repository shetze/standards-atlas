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
        "clause-decision-plan",
        "standards_atlas.application.semantic_qualification.taxonomy_decisions:ClauseDecisionPlan",
    ),
    ModelBinding(
        "formal-ontology-resource",
        "standards_atlas.application.formal_semantics.ontology_definition:FormalOntologyDefinition",
    ),
    ModelBinding(
        "knowledge-adoption-batch",
        "standards_atlas.application.model.knowledge_adoption:KnowledgeAdoptionBatch",
    ),
    ModelBinding(
        "knowledge-adoption-report",
        "standards_atlas.application.model.knowledge_adoption:KnowledgeAdoptionReport",
    ),
    ModelBinding(
        "knowledge-evidence",
        "standards_atlas.adapters.atlasdata.knowledge_contract:EvidenceBlob",
    ),
    ModelBinding(
        "mixed-consensus",
        "standards_atlas.application.semantic_qualification.mixed_evidence:MixedConsensusReport",
    ),
    ModelBinding(
        "ontology-resource",
        "standards_atlas.application.semantic_ontology.definition:OntologyDefinition",
    ),
    ModelBinding(
        "partial-qualification-campaign",
        "standards_atlas.application.semantic_qualification.campaign_contract:"
        "QualificationCampaignArtifact",
    ),
    ModelBinding(
        "partial-qualification-manifest",
        "standards_atlas.application.semantic_qualification.qualification_campaign_model:"
        "QualificationCampaign",
    ),
    ModelBinding(
        "partial-request-plan",
        "standards_atlas.application.semantic_qualification.partial_observations:"
        "PartialRequestPlan",
    ),
    ModelBinding(
        "partial-review-archive",
        "standards_atlas.application.semantic_qualification.review_package.archive:"
        "ReviewArchiveManifest",
    ),
    ModelBinding(
        "partial-review-candidates",
        "standards_atlas.application.semantic_qualification.review_package.preparation_model:"
        "CandidateIndex",
    ),
    ModelBinding(
        "partial-review-handoff",
        "standards_atlas.application.semantic_qualification.review_package.handoff:ReviewHandoff",
    ),
    ModelBinding(
        "partial-review-package",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewPackage",
    ),
    ModelBinding(
        "partial-review-profile",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewProfile",
    ),
    ModelBinding(
        "partial-review-publication",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewPublication",
    ),
    ModelBinding(
        "partial-review-selection-proposal",
        "standards_atlas.application.semantic_qualification.review_package.preparation_model:"
        "SelectionProposal",
    ),
    ModelBinding(
        "partial-review-state",
        "standards_atlas.application.semantic_qualification.review_package.model:ReviewState",
    ),
    ModelBinding(
        "partial-review-workbench-evidence",
        "standards_atlas.application.semantic_qualification.review_package.model:WorkbenchEvidence",
    ),
    ModelBinding(
        "partial-semantic-observation",
        "standards_atlas.application.semantic_qualification.partial_observations:"
        "PartialObservation",
    ),
    ModelBinding(
        "partial-semantic-reference",
        "standards_atlas.application.semantic_qualification.qualification_campaign_model:"
        "SemanticReferenceSuite",
    ),
    ModelBinding(
        "qualification-consensus",
        "standards_atlas.application.semantic_qualification.consensus:ConsensusReport",
    ),
    ModelBinding(
        "qualification-matrix-manifest",
        "standards_atlas.application.semantic_qualification.qualification_matrix:"
        "QualificationMatrixManifest",
    ),
    ModelBinding(
        "qualification-matrix-report",
        "standards_atlas.application.semantic_qualification.qualification_matrix:"
        "QualificationMatrixReport",
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
        "semantic-profile-resource",
        "standards_atlas.application.semantic_classification.profile:SemanticProfile",
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
        "taxonomy-decision-rules",
        "standards_atlas.application.semantic_qualification.taxonomy_decisions:TaxonomyRuleProfile",
    ),
)


SCHEMA_WRITER_BINDINGS: tuple[WriterBinding, ...] = (
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
        "clause-decision-plan",
        "standards_atlas.application.semantic_qualification.taxonomy_diagnostics:"
        "diagnose_taxonomy_decisions",
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
        "partial-cascade-audit",
        "standards_atlas.application.semantic_qualification.partial_cascade_audit:"
        "audit_partial_cascade",
    ),
    WriterBinding(
        "partial-cascade-report",
        "standards_atlas.application.semantic_qualification.partial_cascade:_write_report",
    ),
    WriterBinding(
        "partial-cascade-run",
        "standards_atlas.application.semantic_qualification.partial_cascade:run_partial_cascade",
    ),
    WriterBinding(
        "partial-proposal-run",
        "standards_atlas.application.semantic_qualification.partial_proposals:"
        "run_partial_proposals",
    ),
    WriterBinding(
        "partial-qualification-evaluation",
        "standards_atlas.application.semantic_qualification.campaign_evaluation:evaluate_campaign",
    ),
    WriterBinding(
        "partial-qualification-execution",
        "standards_atlas.application.semantic_qualification.campaign_execution:run_campaign",
    ),
    WriterBinding(
        "partial-qualification-repeat",
        "standards_atlas.application.semantic_qualification.campaign_execution:run_campaign",
    ),
    WriterBinding(
        "partial-qualified-activation",
        "standards_atlas.application.semantic_qualification.campaign_activation:activate_campaign",
    ),
    WriterBinding(
        "qualification-request-event",
        "standards_atlas.application.semantic_qualification.campaign_execution:"
        "FreshLedgerGateway.generate_structured",
    ),
    WriterBinding(
        "semantic-extraction",
        "standards_atlas.adapters.filesystem.semantic_extraction_repository:"
        "FileSystemSemanticExtractionRepository.save",
    ),
    WriterBinding(
        "semantic-extraction",
        "standards_atlas.cli.commands.evaluation_commands.qualification_archive:"
        "finalize_qualification_archive",
    ),
    WriterBinding(
        "semantic-readiness-checks",
        "standards_atlas.application.semantic_qualification.taxonomy_pilot:build_taxonomy_pilot",
    ),
    WriterBinding(
        "semantic-readiness-evaluation",
        "standards_atlas.application.semantic_qualification.semantic_readiness:"
        "evaluate_semantic_readiness",
    ),
    WriterBinding(
        "taxonomy-decision-report",
        "standards_atlas.application.semantic_qualification.taxonomy_diagnostics:"
        "diagnose_taxonomy_decisions",
    ),
    WriterBinding(
        "taxonomy-pilot-readiness",
        "standards_atlas.application.semantic_qualification.taxonomy_pilot:build_taxonomy_pilot",
    ),
)


SCHEMA_RESOURCE_BINDINGS: tuple[ResourceBinding, ...] = (
    ResourceBinding(
        "semantic-task-resource",
        "src/standards_atlas/resources/semantic/tasks/**/task.yaml",
        None,
    ),
    ResourceBinding(
        "semantic-profile-resource",
        "src/standards_atlas/resources/semantic/profiles/**/profile.yaml",
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
        "taxonomy-decision-rules",
        "src/standards_atlas/resources/semantic/taxonomy-decisions/**/rules.yaml",
        None,
    ),
    ResourceBinding(
        "taxonomy-decision-review",
        "src/standards_atlas/resources/semantic/taxonomy-decisions/**/review.yaml",
        None,
    ),
    ResourceBinding(
        "taxonomy-readiness-cases",
        "src/standards_atlas/resources/semantic/qualification/taxonomy-readiness-v1/cases.yaml",
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
    ResourceBinding(
        "partial-qualification-manifest",
        "cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml",
        None,
    ),
    ResourceBinding(
        "partial-review-profile",
        "cfg/evaluation/partial-cascade/review-profile-v1.yaml",
        None,
    ),
)
