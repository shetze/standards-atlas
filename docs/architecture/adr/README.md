# Architecture Decision Records

Architecture Decision Records (ADRs) document important design choices, their context, consequences, and alternatives. The records are chronological, while this index groups them by concern so related decisions can be read together.

## Foundations and system boundaries

| ADR | Decision |
|---|---|
| [0001](0001-python-project-structure-with-uv.md) | Adopt a standard Python project structure using `uv` |
| [0002](0002-adopt-traceability-centric-architecture.md) | Adopt a traceability-centric architecture |
| [0003](0003-adopt-hexagonal-architecture.md) | Adopt a hexagonal architecture |
| [0004](0004-adopt-transformation-pipeline.md) | Adopt a transformation pipeline |
| [0005](0005-separate-public-and-local-content.md) | Separate public and local document content |
| [0006](0006-engineeringdocument-as-canonical-repesenation.md) | Use `EngineeringDocument` as the canonical intermediate representation |
| [0007](0007-structured-clause-content-and-private-source-provenance.md) | Preserve structured clause content and private source provenance; legacy `Clause.text` migration provision superseded |

## Extraction and normalized document evidence

| ADR | Decision |
|---|---|
| [0008](0008-use-docling-as-pdf-extraction-adapter.md) | Use Docling as the PDF extraction adapter |
| [0009](0009-harden-docling-extraction-boundary.md) | Harden the Docling extraction boundary |
| [0010](0010-normalize-extracted-documents-before-alignment.md) | Normalize extracted documents before semantic alignment |
| [0013](0013-preserve-page-start-and-term-definition-clause-anchors.md) | Preserve page-start and term-definition clause anchors |
| [0016](0016-require-lossless-extracted-document-normalization.md) | Require lossless extracted-document normalization |
| [0017](0017-model-physical-source-documents-and-recover-bounded-candidates.md) | Model physical source documents and recover bounded candidates |
| [0026](0026-normalized-document-contract.md) | Establish the `NormalizedDocument` contract |
| [0027](0027-preserve-layout-and-structural-evidence.md) | Preserve layout and structural evidence |
| [0028](0028-deterministic-page-furniture-classification.md) | Classify page furniture deterministically |
| [0029](0029-visual-content-contract-and-caption-ownership.md) | Define visual content and caption ownership |
| [0030](0030-hierarchical-list-reconstruction.md) | Reconstruct hierarchical lists from layout evidence |
| [0055](0055-preserve-visual-formulas-before-semantic-transcription.md) | Preserve visual formulas before semantic transcription |
| [0056](0056-enrich-visual-formulas-through-auditable-transcription-artifacts.md) | Enrich visual formulas through auditable transcription artifacts |

## Candidate detection, alignment, and review

| ADR | Decision |
|---|---|
| [0011](0011-detect-reference-candidates-before-alignment.md) | Detect clause-reference candidates before alignment |
| [0012](0012-align-reference-candidates-with-atlasdata-structure.md) | Align reference candidates with AtlasData structure |
| [0014](0014-introduce-alignment-review-and-manual-overrides.md) | Introduce alignment review and manual overrides |
| [0015](0015-use-full-document-markdown-for-alignment-review.md) | Use full-document Markdown for alignment review |

## Engineering-document construction and semantics

| ADR | Decision |
|---|---|
| [0018](0018-enrich-engineering-documents-from-aligned-content-ranges.md) | Enrich engineering documents from aligned content ranges |
| [0020](0020-preserve-heading-semantics-as-legacy-atlasdata-types.md) | Preserve heading semantics as legacy AtlasData types; semantic-role claims superseded by ADR 0050/0051 |
| [0022](0022-extensible-semantic-role-classification.md) | Use extensible semantic-role classification |
| [0033](0033-engineering-document-construction-contract.md) | Establish the engineering-document construction contract |
| [0050](0050-model-structural-profiles-as-independent-taxonomy-dimensions.md) | Model structural profiles as independent taxonomy dimensions |
| [0051](0051-multidimensional-semantic-classification.md) | Use multidimensional semantic classification |
| [0061](0061-modular-deterministic-structural-taxonomy-engine.md) | Execute structural taxonomies through modular deterministic classifiers |
| [0062](0062-separate-semantic-taxonomies-from-semantic-tasks.md) | Version semantic taxonomies independently from semantic tasks |

## AtlasData, multi-part standards, and baseline governance

| ADR | Decision |
|---|---|
| [0019](0019-generate-atlasdata-skeletons-from-docling-headings.md) | Generate AtlasData skeletons from Docling headings |
| [0021](0021-onboard-multipart-standards-and-annexes.md) | Onboard multi-part standards and annexes |
| [0025](0025-atlasdata-compatibility-and-composed-multipart-exports.md) | Preserve AtlasData compatibility in composed multi-part exports |
| [0035](0035-atlasdata-lifecycle-and-baseline-governance.md) | Govern the AtlasData lifecycle and published baselines |

## Workflow, publication, lineage, and qualification

| ADR | Decision |
|---|---|
| [0023](0023-export-engineering-documents-as-markdown.md) | Export engineering documents as Markdown |
| [0024](0024-catalog-driven-end-to-end-workflows.md) | Use catalog-driven end-to-end workflows |
| [0031](0031-deterministic-transformation-ledger.md) | Record a deterministic transformation ledger |
| [0032](0032-end-to-end-artifact-lineage.md) | Preserve end-to-end artifact lineage |
| [0034](0034-golden-corpus-and-regression-qualification.md) | Use a golden corpus for regression qualification |
| [0036](0036-local-workspace-and-hierarchy-publication.md) | Separate internal artifacts from hierarchy-based local publications |
| [0037](0037-workflow-run-derivation-reports.md) | Record workflow-run derivation reports |
| [0038](0038-package-and-install-doorstop-publication-templates.md) | Package and install Doorstop publication templates |
| [0039](0039-verification-and-qualification-framework.md) | Establish the verification and qualification framework |
| [0057](0057-unify-workflow-task-selection-and-manifests.md) | Unify workflow task selection and manifest inputs; manifest-option details superseded by ADR 0058 |
| [0058](0058-typed-workflow-manifest-envelope.md) | Use typed workflow manifests behind the unified `--manifests` option |
| [0059](0059-archive-qualification-runs-as-immutable-sequential-evidence.md) | Archive qualification runs as immutable sequential evidence |
| [0070](0070-preserve-cascade-resolution-provenance.md) | Preserve cascade resolution provenance; administratively renumbered from duplicate 0056 |

## Semantic evaluation, review, and MCP access

| ADR | Decision |
|---|---|
| [0040](0040-expose-evaluation-services-through-an-mcp-adapter.md) | Expose evaluation services through a read-only MCP inbound adapter |
| [0041](0041-keep-semantic-evaluation-data-local-and-reports-content-safe.md) | Keep protected evaluation data local and reports content-safe |
| [0042](0042-secure-and-qualify-streamable-http-mcp-deployments.md) | Secure and qualify Streamable HTTP MCP deployments |
| [0043](0043-integrate-codex-as-a-restricted-mcp-client.md) | Integrate Codex as a restricted MCP client |
| [0044](0044-publish-reviewed-clause-annotations-as-reproducible-data.md) | Publish reviewed clause annotations as reproducible data |
| [0045](0045-build-representative-semantic-evaluation-corpora.md) | Build representative semantic-evaluation corpora by stratified coverage |
| [0046](0046-persist-resumable-semantic-proposal-runs.md) | Persist resumable semantic proposal runs |
| [0047](0047-separate-semantic-evaluation-runs-from-annotations.md) | Separate semantic evaluation runs from reviewed annotations |
| [0048](0048-review-semantic-annotations-in-local-markdown.md) | Review semantic annotations in local Markdown |
| [0049](0049-extract-and-resolve-clause-references-before-semantic-evaluation.md) | Extract and resolve clause references before semantic evaluation |
| [0052](0052-build-golden-corpus-proposals-from-model-consensus.md) | Build Golden Corpus proposals from model consensus |
| [0054](0054-model-engineering-knowledge-as-an-orthogonal-ontology.md) | Model engineering knowledge as an orthogonal ontology |
| [0059](0059-archive-qualification-runs-as-immutable-sequential-evidence.md) | Archive qualification runs as immutable sequential evidence |
| [0060](0060-classify-workspace-artifacts-by-audience-and-lifecycle.md) | Classify generated artifacts by audience and lifecycle |
| [0061](0061-modular-deterministic-structural-taxonomy-engine.md) | Modular deterministic structural-taxonomy engine |
| [0062](0062-separate-semantic-taxonomies-from-semantic-tasks.md) | Separate semantic taxonomies from semantic tasks |
| [0063](0063-schema-compatibility-baseline.md) | Establish a clean schema compatibility baseline |
| [0064](0064-bounded-schema-reader-compatibility.md) | Bound persisted-schema compatibility at the reader boundary |
| [0065](0065-separate-structural-taxonomy-from-semantic-ontology.md) | Separate structural taxonomy from semantic ontology |
| [0066](0066-structural-context-taxonomy-stage.md) | Materialize deterministic structural context in an explicit taxonomy workflow stage |
| [0067](0067-production-ontology-workflow-stage.md) | Run LLM-assisted semantic ontology classification after structural taxonomy |
| [0068](0068-finalize-taxonomy-ontology-stage-ownership.md) | Remove legacy mixed classification and enforce taxonomy/ontology stage ownership |
| [0069](0069-materialize-structural-scope-reach.md) | Materialize structural scope reach in taxonomy |
| [0072](0072-deterministic-taxonomy-aware-semantic-routing-domain.md) | Introduce a deterministic taxonomy-aware semantic routing domain |
| [0073](0073-version-routing-contract-resources-and-manifests.md) | Version routing contracts as resources selected by typed workflow manifests |
| [0074](0074-materialize-semantic-routing-as-workflow-artifacts.md) | Materialize deterministic semantic routing as separate workflow artifacts |

## Application structure

| ADR | Decision |
|---|---|
| [0053](0053-structural-application-refactoring.md) | Refactor CLI, workflow, evaluation, and normalization application structure |

## Decision lifecycle

ADRs are historical records. A later decision does not cause an earlier record to be
rewritten as though the earlier context never existed. Instead, the status and a
supersession or amendment note identify which provisions still describe the current
architecture. The index summaries call out partial supersession where a record contains
both active and obsolete provisions.

## Reading guidance

- For the architecture's overall shape, begin with [ADR 0002](0002-adopt-traceability-centric-architecture.md), [ADR 0003](0003-adopt-hexagonal-architecture.md), and [ADR 0004](0004-adopt-transformation-pipeline.md).
- For the canonical contracts, continue with [ADR 0006](0006-engineeringdocument-as-canonical-repesenation.md), [ADR 0026](0026-normalized-document-contract.md), and [ADR 0033](0033-engineering-document-construction-contract.md).
- For workflow and publication, read [ADR 0024](0024-catalog-driven-end-to-end-workflows.md), [ADR 0032](0032-end-to-end-artifact-lineage.md), [ADR 0035](0035-atlasdata-lifecycle-and-baseline-governance.md), and [ADR 0036](0036-local-workspace-and-hierarchy-publication.md).
- For the current taxonomy-to-ontology production path, read [ADR 0050](0050-model-structural-profiles-as-independent-taxonomy-dimensions.md), [ADR 0051](0051-multidimensional-semantic-classification.md), and [ADR 0061](0061-modular-deterministic-structural-taxonomy-engine.md) through [ADR 0069](0069-materialize-structural-scope-reach.md); use [Structural taxonomy and semantic ontology](../structural-classification.md) as the consolidated current-state view.
- For semantic qualification and external model access, continue with [ADR 0039](0039-verification-and-qualification-framework.md), [ADR 0040](0040-expose-evaluation-services-through-an-mcp-adapter.md), [ADR 0042](0042-secure-and-qualify-streamable-http-mcp-deployments.md), [ADR 0054](0054-model-engineering-knowledge-as-an-orthogonal-ontology.md), [ADR 0059](0059-archive-qualification-runs-as-immutable-sequential-evidence.md), and [ADR 0070](0070-preserve-cascade-resolution-provenance.md).
- For lossless formula handling, read [ADR 0055](0055-preserve-visual-formulas-before-semantic-transcription.md).
- For the current application package structure, read [ADR 0053](0053-structural-application-refactoring.md).

## Related documentation

- [Architecture overview](../README.md)
- [Processing pipeline](../processing-pipeline.md)
- [Domain model](../domain-model.md)
- [Diagram catalog](../diagrams/README.md)
- [Documentation home](../../README.md)

