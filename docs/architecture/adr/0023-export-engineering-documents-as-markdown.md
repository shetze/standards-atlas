# ADR-0023: Export engineering documents as Markdown

## Status

Accepted

## Context

Reviewed and enriched `EngineeringDocument` objects need a human-readable export that can be collected in one common directory. Multi-part standards are represented as one logical document, while their source PDFs and Docling documents remain separate physical parts.

## Decision

Introduce a Markdown exporter adapter implementing the existing `EngineeringDocumentExporter` port and a `MarkdownExportService` that orchestrates family exports.

A single CLI invocation exports a logical standard family. Documents without volumes produce `<document-key>.md`. Documents containing several volumes are split deterministically and produce `<document-key>-<volume>.md` in the same target directory.

The exporter renders clause hierarchy and structured content blocks without using alignment artifacts. The persisted `EngineeringDocument` is the sole export source.

## Consequences

Markdown export is reproducible and independent from the review format. Multi-part standards remain one logical command while preserving their physical file boundaries. Future Markdown variants can replace the adapter without changing family selection or the canonical domain model.

### Clause order and table of contents

Persisted EngineeringDocuments are not required to store clauses in depth-first
reference order. The Markdown adapter therefore sorts clauses by their visible
reference before rendering. Numeric clauses precede annex clauses and natural
numeric ordering is used within each level.

Each exported file contains a generated Markdown table of contents linking to
stable explicit clause anchors. The table of contents includes clauses up to the
fourth clause level. Deeper clauses remain part of the document but are omitted
from the table of contents.

Foreword and introduction clauses are omitted when represented by their semantic
roles. Editorial source material that is not part of the EngineeringDocument is
not exported.
