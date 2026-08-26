# ADR 0080: Normalize tables before semantic interpretation

- Status: Accepted
- Date: 2026-08-26

## Context

T1 made tables first-class document structure while keeping protected rows and cells canonical
in `TableBlock`. Raw table cells still expose adapter-level layout details: merged headers are
represented by spans, row-header scope is implicit, units are embedded in labels, and footnotes
or references are mixed with ordinary cell text. Semantic table mapping and retrieval should not
have to reconstruct those details independently.

## Decision

Standards Atlas introduces a deterministic, semantics-free `NormalizedTable` projection between
`TableBlock` and downstream knowledge mapping.

- `TableBlock` remains the canonical protected source content.
- `DocumentTable` remains the canonical document-level table identity from T1.
- `NormalizedTable` is a reproducible projection; it is not independently edited or persisted.
- Span-aware normalization places anchor cells at stable logical row/column coordinates and
  reconstructs the effective rectangular grid.
- Consecutive leading header rows become hierarchical `header_path` values per logical column.
- Row-header cells, including row-spanning headers, become row `header_path` values.
- Units are extracted conservatively from header labels while original header text is retained.
- Structurally recognizable table footnotes are separated without deleting their source rows.
- Table, clause, and standard references are tokenized with source coordinates but remain
  unresolved and semantically uninterpreted.
- Source evidence, original cell text, spans, table identity, and parent-clause identity are
  preserved.

A read-only filesystem adapter exposes normalized tables by regenerating them from persisted
engineering documents. No normalized-table persistence schema is introduced.

T2 does not infer table kind, recommendation semantics, roles, techniques, applicability, or
ontology relations. Mapping normalized structure into `StructuredKnowledgeRecord` belongs to T3.
Retrieval serialization, table-specific tokenization, and embeddings belong to T4.

## Consequences

Downstream table processing receives one stable structural representation independent of Docling
layout quirks. Semantic mappers can reason over explicit columns and row/header paths instead of
reimplementing merge handling. Retrieval adapters can later choose table-, row-, or cell-level
serializations without becoming authoritative data stores.
