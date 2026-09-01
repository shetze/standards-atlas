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

`governance profile select` writes deterministic `candidate-analysis.json` plus a review-oriented
CSV. `governance profile export-policy` writes a Gemara Policy scaffold and a sidecar that records
withheld/undetermined decisions.

## ComplyPack authoring workspace

`document export complypack` writes copied evaluator policy content, `complypack.yaml`, the
governance bundle, `workspace-manifest.yaml`, and lineage. The workspace manifest binds governance,
configuration, and evaluator content by SHA-256.

## ComplyTime evaluation feedback

`evaluation complytime-feedback` writes a derived JSON report resolving EvaluationLog entries back
to source clauses. It is evidence/reporting and is not imported into the canonical document.
