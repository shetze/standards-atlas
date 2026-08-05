# Table semantics

Standards frequently encode their most valuable relationships in tables rather than in
standalone prose. Flattening a complete annex or matrix into one clause string preserves
characters but destroys row, column, context, and relationship semantics. Standards Atlas
therefore treats table interpretation as a separate semantic path beside clause
classification.

## Architectural boundary

```text
EngineeringDocument
└── Clause
    └── TableBlock                 canonical source
        └── KnowledgeTable         deterministic projection
            └── KnowledgeRecord    addressable logical row
                ├── original cells and evidence
                └── optional interpreted knowledge
```

`TableBlock` remains part of the canonical `EngineeringDocument`. `KnowledgeTable` and
`KnowledgeRecord` are reproducible projections, not independently edited copies. This
keeps normalization and provenance authoritative while allowing MCP, graph, and future RAG
consumers to retrieve table knowledge at useful granularity.

## Stable identity and evidence

Table and record IDs are derived deterministically from document identity, clause identity,
table position, and row position. Projections preserve captions, headers, cell text, row
and column spans, and source evidence. Semantic concepts additionally record the exact
source column from which they were derived.

This evidence-first model makes it possible to present the original row, explain a derived
relationship, retrieve neighbouring records, and regenerate future index representations
without treating an embedding chunk as authoritative.

## Interpretation layers

### IEC 61508 recommendation matrices

IEC 61508-3 Annex A matrices are recognized conservatively. The projection normalizes
`HR`, `R`, `—`, and `NR`, retains the source marker, associates recommendations with SIL
levels, resolves IEC 61508-7 description references, resolves table-context clauses, and
recognizes alternative groups such as `1a` and `1b`.

### Portable table ontology

Header-driven schema recognition supports:

- work-product matrices: activity `produces` work product;
- responsibility matrices: role `responsible_for` activity;
- verification-criteria matrices: subject `verified_by` criterion;
- traceability matrices: source `traces_to` target;
- applicability matrices: subject `applicable_to` context.

Schemas are applied only when required headers and non-empty row values are present. An
ambiguous table remains `generic`; the implementation does not infer relations merely
because cell values look plausible.

## Separation from clause semantics

Statement functions describe the linguistic function of narrative clauses. Matrix kind,
recommendation level, and row relationships are different semantic dimensions. Table
relations therefore must not be projected back into `SemanticClassification` labels of the
surrounding clause.

A central `SemanticTaskEligibilityPolicy` excludes `table_dominant` content from
`statement-function-classification` and records `structured-table-interpretation` as the
alternative task. Text-dominant mixed clauses remain eligible, but prompts require models
to classify only their narrative content.

## Retrieval and IntelliDoc

The MCP adapter exposes tables and records directly. Future IntelliDoc RAG indexes should
use reproducible text projections at several granularities—table, record, and relation—while
retaining stable IDs back to the structured artefacts. Embedding chunks are disposable
index projections; the Knowledge Base and its source evidence remain authoritative.

## Current limitation

Projection and interpretation are implemented and covered by deterministic tests. A
dedicated `structured-table-interpretation` corpus, golden data workflow, model
qualification matrix, and HITL review flow are planned but not yet implemented. See the
[structured table corpus roadmap](../roadmap/structured-table-corpora.md).
