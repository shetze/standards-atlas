# ADR 0018 – Enrich EngineeringDocuments from Aligned Content Ranges

- **Status:** Accepted
- **Date:** 2026-07-18

## Context

The normalization and alignment pipeline now identifies the start of every
logical clause in a physical source document. AtlasData supplies the public
clause structure, stable identifiers, hierarchy and generated titles, while the
normalized document retains the protected text, lists, tables, pictures,
formulas, code and source provenance.

The canonical `EngineeringDocument` already supports structured
`Clause.content` through the ContentBlock model introduced by ADR 0007. Until
now, however, the aligned normalized content was not transferred into that
model. Exporters therefore still operated on an EngineeringDocument containing
structure but no extracted clause bodies.

Markdown is unsuitable as the source for this enrichment. It is a review
surface and intentionally loses normalized item types and source provenance.
The alignment result already contains deterministic clause ranges through
`start_sequence_number` and `end_sequence_number`.

## Decision

Introduce a dedicated `ContentEnrichmentService` as the Slice 5 application
service.

The service loads:

1. the persisted `EngineeringDocument`,
2. the `NormalizedExtractedDocument`, and
3. `reviewed.json` when available, otherwise `alignment.json`.

For every aligned clause, the inclusive normalized range is converted in order
to canonical ContentBlocks:

- `NormalizedText` and body headings become `TextBlock`,
- `NormalizedList` becomes `ListBlock`,
- `NormalizedTable` becomes `TableBlock`,
- `NormalizedPicture` becomes `PictureBlock`,
- `NormalizedFormula` becomes `FormulaBlock`, and
- `NormalizedCode` becomes `CodeBlock`.

Source evidence is copied unchanged to each generated block. ContentBlock IDs
are deterministic and derived from normalized item IDs.

The first normalized item in a clause range is treated as the structural clause
head. A heading or reference-only anchor is omitted from `Clause.content` to
avoid duplicating the clause reference and title. When the reference occurs at
the beginning of a body paragraph, the detected inline remainder becomes the
first TextBlock.

The enriched document is persisted back to `.atlas/documents/<key>.json`.
Because `.atlas` is private and ignored by Git, protected standard content does
not enter the public repository.

By default enrichment aborts when alignments remain missing, ambiguous or
conflicting. Low-confidence and inferred alignments are accepted because they
represent explicit bounded ranges and remain traceable through the alignment
artifact. A caller may explicitly allow unresolved clauses; those clauses then
remain unchanged.

## Consequences

### Advantages

- `EngineeringDocument` becomes the complete canonical input for exporters.
- Structured content and provenance survive the transition from Docling.
- Range partitioning is deterministic and reproducible.
- Clause headings are not duplicated as normative body content.
- Existing Doorstop and future Markdown/HTML exporters can consume the same
  canonical model.
- Reviewed alignment is used automatically when present.

### Disadvantages

- Enrichment mutates the persisted canonical document and must be rerun after
  normalization or alignment changes.
- Some normalized headings inside a clause may represent semantic substructure
  that is currently projected to TextBlock; richer nested block semantics may
  be introduced later.
- Unassigned front and back matter is not attached to clauses in this slice.

## Slice 5 Boundary

Slice 5 includes deterministic range-to-ContentBlock enrichment, persistence,
CLI integration, validation and tests. It does not include new export formats,
semantic classification of notes, or reconstruction of nested clause
hierarchies from body headings.

## Relationship to Previous ADRs

- ADR 0003 defines the hexagonal architecture.
- ADR 0004 defines the transformation pipeline.
- ADR 0005 separates public and protected private content.
- ADR 0007 defines ContentBlocks and SourceEvidence.
- ADR 0018 completes the alignment-to-canonical-content transition.
