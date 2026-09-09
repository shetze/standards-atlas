# Artifact formats

## AtlasData

Versioned public baseline containing metadata, compiled structure, clause types, headings, lifecycle status, and permitted public annotations.

## Docling artefact

Native private extraction JSON plus conversion metadata. It is adapter-specific evidence, not a canonical engineering document.

## Normalization artefact

Stable normalized content, source anchors, layout evidence, transformation ledger, and validation statistics.

## Reference candidates

Detected identifiers and anchors with source locations and evidence.

## Alignment artefacts

Machine proposal, review document, manual overrides, and reviewed result are stored separately so decisions remain auditable.

## EngineeringDocument

Canonical JSON persisted by the filesystem repository. It contains adapter-neutral metadata, clauses, content blocks, annotations, relations, and lineage.

## Export artefacts

Markdown and Doorstop are generated projections. They may be deleted and regenerated when their canonical input and configuration are unchanged.

## Gemara governance artifacts

`document export gemara` writes a GuidanceCatalog and SHA-256-bound traceability sidecar.
`document export gemara-controls` writes a linked ControlCatalog and its sidecar. Catalog and entry
identities are deterministic projections of Standards Atlas identities.

## ComplyTime governance bundle

`document export complytime` writes `guidance.yaml`, `controls.yaml`, `traceability.json`,
`manifest.yaml`, and `lineage.json`. The manifest hashes the hand-off artifacts; consolidated
traceability supports later EvaluationLog feedback resolution.

## Governance selection artifacts

`governance profile select` writes Candidate Analysis schema v2 as deterministic
`candidate-analysis.json` plus a review-oriented CSV. The analysis records resolved Subject Groups,
effective Primary Subjects, clause-local selector signals, matching Clause IDs, and undetermined
Clause IDs. The CSV exposes the same provenance for HITL review.

`governance profile export-policy` writes a Gemara Policy scaffold and a schema-v2 sidecar. The
sidecar binds selected/withheld Controls to the clause-local evidence and resolved Subject Group
Profile used to create the draft.

## ComplyPack authoring workspace

`document export complypack` writes copied evaluator policy content, `complypack.yaml`, the
governance bundle, `workspace-manifest.yaml`, and lineage. The workspace manifest binds governance,
configuration, and evaluator content by SHA-256.

## ComplyTime evaluation feedback

`evaluation complytime-feedback` writes a derived JSON report resolving EvaluationLog entries back
to source clauses. It is evidence/reporting and is not imported into the canonical document.

## Qualification consensus and process observations

Consensus schema 5.0 preserves process sets and primaries independently, including availability,
participation, per-label/primary support, exact-set agreement and resolution sources. A missing
set is not an empty selection, and an undecided primary is not an explicit null vote. Annotation
generators record `provided_fields` before normalization defaults are added.

Schema 4.0 consensus remains readable without changing old policy hashes. Only matching retained
structured provider responses can supply missing observations during explicit recomputation.
Free-text rationale and old synthesized interview defaults are not evidence for this purpose.
The human-review golden proposal is now schema 4.0; the qualification archive layout stays 1.5.
See [Process-function qualification](../user-guide/process-function-qualification.md).
