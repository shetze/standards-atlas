# ADR 0010: First-Class Tables and Structured Knowledge

## Status
Accepted

## Goal alignment
Tables are evidence-bearing structures that can contribute directly to machine-processable knowledge. Preserving their deterministic structure before semantic interpretation supports qualified ABox extraction and keeps downstream RAG/GraphRAG representations replaceable.

## Context
Normative standards frequently encode requirements, techniques, measures, mappings, and applicability rules in tables. Treating tables as plain text loses row/column semantics and causes poor extraction behavior.

## Decision
Tables are first-class structural evidence and flow through a deterministic staged model:

```text
source table -> DocumentTable -> NormalizedTable -> StructuredKnowledgeRecord -> retrieval projection
```

- `DocumentTable` preserves source identity, location, caption, cells, spans, and structural ownership.
- `NormalizedTable` provides deterministic row/column semantics and normalized headers without discarding source evidence.
- Domain-specific deterministic mapping may produce `StructuredKnowledgeRecord` instances for supported table patterns.
- Retrieval/GraphRAG projections are derived and replaceable.
- LLM extraction may consume normalized tables, but does not define canonical table structure.

## Consequences
Large normative tables can be processed structurally, deterministically, and efficiently while retaining traceability to source cells.
