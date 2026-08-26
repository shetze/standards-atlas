# ADR 0082: Project structured tables for retrieval behind replaceable ports

## Status

Accepted.

## Context

T1-T3 preserve table identity, normalize protected cells, and map deterministic structured
knowledge. Retrieval systems need representations optimized for indexing, tokenization, and
embedding, but those representations must not become another authoritative copy of standards
knowledge. Tables also require a different serialization/tokenization contract from narrative
clauses because headers, rows, concepts, and relations carry meaning independently.

## Decision

Introduce a T4 retrieval projection layer. `TableRetrievalProjectionService` derives
`RetrievalDocument` values at table, row, concept, and relation granularity from T3
`KnowledgeTable` artifacts. Each document carries stable source identity, metadata, deterministic
text, and the `structured-table-v1` tokenization profile.

Tokenizer and downstream index ownership remain ports. A retrieval adapter may use a table-aware
model tokenizer, vector database, graph index, or hybrid retrieval implementation without
changing T1-T3 artifacts. The filesystem adapter exposes reproducible projections on demand; it
does not persist embeddings or make retrieval chunks canonical.

## Consequences

- narrative and table retrieval can use different tokenizer implementations;
- table, row, concept, and relation embeddings can coexist and be compared independently;
- every retrieval hit retains a stable source id back to structured knowledge and source evidence;
- vector stores and GraphRAG implementations remain replaceable adapters;
- changes to an embedding model or tokenizer require rebuilding projections/indexes, not migrating
  `EngineeringDocument`, `TableBlock`, `NormalizedTable`, or `StructuredKnowledgeRecord` data.
