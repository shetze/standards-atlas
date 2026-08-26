# ADR 0079: Capture tables as first-class document structure

- Status: Accepted
- Date: 2026-08-26

## Context

Standards contain semantically important tables with their own captions, numbering,
structural parents, and entries in a List of Tables. Treating a table only as a
`TableBlock` nested in clause content loses document-level identity and encourages later
semantic stages to flatten table collections into narrative text. IEC 61508-3 Annex A is
a representative case: the source already provides structured technique matrices and
should not be reconstructed from a large text projection.

## Decision

Tables are first-class structural entities in `EngineeringDocument`.

- `DocumentTable` records stable table identity, reference, title, structural parent,
  sequence position, source evidence, and the linked canonical `TableBlock` identifier.
- `TableIndexEntry` records declarations from the document's List of Tables and resolves
  to `DocumentTable` when the table is available.
- AtlasData carries only public table structure through `TABLE` and `TABLEINDEX` records.
  Cell content is never copied into AtlasData.
- Docling onboarding discovers table captions, nearest clause/annex parents, and List of
  Tables entries and emits those public records.
- Content enrichment links protected `TableBlock` content to the first-class structural
  table metadata.
- Engineering-document persistence advances to schema 5; schemas 3 and 4 remain readable.

T1 does not normalize merged headers, row hierarchies, footnotes, or table semantics.
Those concerns remain in subsequent table-normalization and structured-knowledge slices.
Retrieval serialization and embedding are also explicitly outside this decision.

## Consequences

Table identity is available before semantic interpretation, public AtlasData baselines can
be checked against declared Lists of Tables, and narrative semantic extraction can later
route table-dominant structures away from the text path. `TableBlock` remains the
canonical holder of protected cells, avoiding two competing content representations.
