# Structured table corpora and qualification

## Motivation

The current table projection preserves and interprets important matrix knowledge, but the
evaluation framework remains centered on clause corpora. Table schema recognition, row
extraction, relation extraction, and specialized recommendation interpretation require
different input artefacts, labels, metrics, and review workflows. Flattened clauses must
not be reintroduced as a shortcut.

## Current state

Version 0.8.0 provides:

- detection of `table_dominant` clauses;
- central eligibility routing away from statement-function classification;
- deterministic `KnowledgeTable` and `KnowledgeRecord` projections;
- stable IDs, cells, spans, captions, and source evidence;
- IEC 61508-3 recommendation-matrix interpretation;
- a portable ontology for work-product, responsibility, verification, traceability, and
  applicability matrices;
- read-only MCP access to tables and records.

The existing statement-function command remains valid:

```bash
uv run standards-atlas evaluation corpus-build \
  --task statement-function-classification \
  --version 2.0.0 \
  --corpus-id statement-functions-v2 \
  --knowledge-domain functional-safety \
  --count 500 \
  --strategy representative_stratified \
  --seed 20260804
```

It must continue to exclude table-dominant clauses by default.

## Target command

Introduce a table-aware corpus builder while retaining the common evaluation command
surface:

```bash
uv run standards-atlas evaluation corpus-build \
  --task structured-table-interpretation \
  --version 1.0.0 \
  --corpus-id structured-tables-v1 \
  --knowledge-domain functional-safety \
  --count 200 \
  --strategy representative_stratified \
  --seed 20260804
```

The task selects `KnowledgeTable` artefacts rather than clauses. `--count` counts tables,
and stratification uses table kind, document family, annex/normative context, table size,
and interpretation confidence. Record-level subtasks may derive bounded samples from the
selected tables without losing table context.

## Target task family

### Table schema classification

Determine whether a table is generic or one of the supported matrix kinds. Gold data must
include explicit `generic` and ambiguous examples to measure over-classification.

### Record extraction

Verify logical row boundaries, header propagation, merged-cell handling, captions, notes,
and source evidence. Metrics include row recall, cell alignment, span preservation, and
evidence completeness.

### Relation extraction

Evaluate concepts and evidence-backed relationships such as `produces`,
`responsible_for`, `verified_by`, `traces_to`, and `applicable_to`. Report precision and
recall separately and reject relations without source-column provenance.

### Recommendation-matrix interpretation

Evaluate IEC 61508-specific local IDs, alternative groups, SIL columns, normalized
recommendation values, context clauses, and IEC 61508-7 description references.

## Corpus and artifact contracts

A table dataset item should contain:

- stable table ID, document key, parent clause, reference, caption, and table kind;
- normalized headers and original row/cell structure;
- source evidence suitable for protected local review;
- expected schema and optional expected record semantics;
- content hashes for copyright-safe manifests;
- eligibility and exclusion evidence.

Gold labels, model proposals, reviewer decisions, and published regression fixtures remain
separate artefacts. Local protected text must not leak into publishable reports.

## CLI and architecture changes

1. Generalize corpus providers from clause-only access to typed evaluation items.
2. Register task input kinds such as `clause` and `knowledge_table`.
3. Select the provider from task metadata rather than a task-name conditional.
4. Add table-aware representative stratification and deterministic sampling.
5. Add table proposal schemas, metrics, consensus, and HITL renderers.
6. Extend qualification manifests to compare deterministic baselines and optional LLM
   interpreters.
7. Preserve the existing statement-function CLI and corpus contracts.

## Milestones

### Milestone 1 — Typed corpus infrastructure

Introduce an evaluation-item protocol and a `KnowledgeTableProvider`; produce a hashed
annotation-ready table corpus and manifest.

### Milestone 2 — Golden table schema corpus

Create a representative reviewed corpus across IEC 61508 and other functional-safety
standards. Qualify schema recognition against generic and ambiguous controls.

### Milestone 3 — Record and relation qualification

Add cell/row alignment metrics, concept/relation metrics, and source-evidence checks.
Provide a table-oriented HITL review document.

### Milestone 4 — Specialized interpreters

Qualify IEC 61508 recommendation matrices and add additional domain adapters only when a
reviewed corpus demonstrates stable semantics.

### Milestone 5 — IntelliDoc/RAG projection

Generate deterministic retrieval documents at table, record, and relation granularity.
Expose semantic search through MCP while preserving links to canonical evidence.

## Risks

- merged cells and repeated headers can create false row boundaries;
- table captions may not uniquely identify context;
- header-only schema matching may over-classify unrelated tables;
- small specialized corpora can hide document-family bias;
- RAG text projections can omit qualifiers unless generated from structured records;
- copyrighted table content requires the same local-data controls as clause corpora.

## Success criteria

- statement-function corpora contain no table-dominant artefacts by default;
- table corpus builds are deterministic for a fixed workspace, strategy, count, and seed;
- every interpreted concept and relation links to original cells and source evidence;
- qualification reports distinguish schema, extraction, relation, and reference quality;
- reviewed table artefacts can be retrieved through MCP without reconstructing tables from
  flattened prose;
- future RAG indexes can be regenerated without changing the canonical Knowledge Base.
