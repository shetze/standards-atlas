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
