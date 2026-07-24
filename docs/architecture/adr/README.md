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
| [0007](0007-structured-clause-content-and-private-source-provenance.md) | Preserve structured clause content and private source provenance |

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
| [0020](0020-preserve-heading-semantics-as-legacy-atlasdata-types.md) | Preserve heading semantics as legacy AtlasData types |
| [0022](0022-extensible-semantic-role-classification.md) | Use extensible semantic-role classification |
| [0033](0033-engineering-document-construction-contract.md) | Establish the engineering-document construction contract |

## AtlasData, multi-part standards, and baseline governance

| ADR | Decision |
|---|---|
| [0019](0019-generate-atlasdata-skeletons-from-docling-headings.md) | Generate AtlasData skeletons from Docling headings |
| [0021](0021-onboard-multipart-standards-and-annexes.md) | Onboard multi-part standards and annexes |
| [0025](0025-atlasdata-compatibility-and-composed-multipart-exports.md) | Preserve AtlasData compatibility in composed multi-part exports |
| [0035](0035-atlasdata-lifecycle-and-baseline-governance.md) | Govern the AtlasData lifecycle and published baselines |

## Workflow, export, lineage, and qualification

| ADR | Decision |
|---|---|
| [0023](0023-export-engineering-documents-as-markdown.md) | Export engineering documents as Markdown |
| [0024](0024-catalog-driven-end-to-end-workflows.md) | Use catalog-driven end-to-end workflows |
| [0031](0031-deterministic-transformation-ledger.md) | Record a deterministic transformation ledger |
| [0032](0032-end-to-end-artifact-lineage.md) | Preserve end-to-end artifact lineage |
| [0034](0034-golden-corpus-and-regression-qualification.md) | Use a golden corpus for regression qualification |

## Reading guidance

- For the architecture's overall shape, begin with [ADR 0002](0002-adopt-traceability-centric-architecture.md), [ADR 0003](0003-adopt-hexagonal-architecture.md), and [ADR 0004](0004-adopt-transformation-pipeline.md).
- For the canonical contracts, continue with [ADR 0006](0006-engineeringdocument-as-canonical-repesenation.md), [ADR 0026](0026-normalized-document-contract.md), and [ADR 0033](0033-engineering-document-construction-contract.md).
- For operational governance, read [ADR 0024](0024-catalog-driven-end-to-end-workflows.md), [ADR 0032](0032-end-to-end-artifact-lineage.md), [ADR 0034](0034-golden-corpus-and-regression-qualification.md), and [ADR 0035](0035-atlasdata-lifecycle-and-baseline-governance.md).

## Related documentation

- [Architecture overview](../README.md)
- [Processing pipeline](../processing-pipeline.md)
- [Domain model](../domain-model.md)
- [Diagram catalog](../diagrams/README.md)
- [Documentation home](../../README.md)
