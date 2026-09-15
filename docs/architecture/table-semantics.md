# Table semantics

Standards frequently encode their most valuable relationships in tables rather than in
standalone prose. Flattening a complete annex or matrix into one clause string preserves
characters but destroys row, column, context, and relationship semantics. Standards Atlas
therefore treats table interpretation as a separate semantic path beside clause
classification.

## Architectural boundary

```text
EngineeringDocument
├── tables: DocumentTable          first-class structural identity
├── table_index: TableIndexEntry   List-of-Tables declarations
└── Clause
    └── TableBlock                 canonical protected cells
        └── NormalizedTable        T2 structural normalization
            ├── logical columns/header paths
            ├── rows/cells/spans/footnotes/references
            └── StructuredKnowledgeMappingService   T3 deterministic semantic mapping
                └── KnowledgeTable / KnowledgeRecord
                    └── StructuredKnowledgeRecord
                        └── TableKnowledgeProposalProjector
                            └── DocumentKnowledgeProposal
                                └── DocumentKnowledgeProposalUnifier
                                    └── unified DocumentKnowledgeProposal
```

`DocumentTable` owns document-level table identity, numbering, caption metadata, parent
structure, and sequence. `TableIndexEntry` captures the independently declared List of
Tables. Protected rows and cells remain canonical in `TableBlock`; `DocumentTable` links to
that block by identifier instead of duplicating its content. T2 derives a semantics-free
`NormalizedTable` that reconstructs logical coordinates and header structure while preserving
all protected text and spans. `KnowledgeTable` and `KnowledgeRecord` remain reproducible
semantic projections, not independently edited copies. T3 consumes only `NormalizedTable`; the
historical projection service is a compatibility facade over the T2 → T3 path. Slice 6A adds a
deterministic proposal projection for supported portable matrices so prose and table knowledge use
the same `KnowledgeEntityProposal` / `NormativeAssertionProposal` contracts before qualification. The
table projector emits a distinct run-scoped proposal with deterministic projector provenance.
Slice 6B combines prose and table runs only through a deterministic proposal unifier that preserves
direct input-run hashes/provenance and performs document-local entity resolution before later
qualification. Slice 6C completes the deterministic table proposal path for IEC 61508 qualified technique recommendations by reifying the n-ary recommendation rather than flattening its qualifier into one binary predicate.

AtlasData publishes table structure through `TABLE` and `TABLEINDEX` records only. It never
publishes table cells. This allows onboarding and review to compare declared and detected
tables before private content enrichment.

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

IEC 61508-3 Annex A matrices are recognized conservatively from normalized header paths. T3
normalizes `HR`, `R`, `—`, and `NR`, retains the source marker, associates recommendations with SIL
levels, tokenizes IEC 61508-7 description references and table-context clauses, and recognizes
alternative groups such as `1a` and `1b`. Each technique and integrity level is also exposed as a
`KnowledgeConcept`; `recommended_for` relations carry the normalized recommendation level as a
qualifier. This avoids treating an Annex full of tables as one narrative LLM extraction unit.

### Portable table ontology

Header-driven schema recognition supports the existing deterministic T3 relations:

- work-product matrices: activity `produces` work product;
- responsibility matrices: role `responsible_for` subject;
- verification-criteria matrices: subject `verified_by` criterion;
- traceability matrices: source `traces_to` target;
- applicability matrices: subject `applicable_to` context.

Slice 6A projects the first four engineering matrix kinds (excluding applicability) into Formal
Ontology 2.0 proposal assertions. The resulting directions are `WorkProduct producedBy Activity`,
`Role responsibleFor EngineeringEntity`, source `tracesTo` target, and subject `requires Criterion`.
No normative force is inferred from matrix shape, so these deterministic assertions use
`unspecified` force until qualification/adoption supplies stronger authority. Applicability remains
CBox-oriented and is deliberately not projected by the 6A engineering-knowledge projector.

Slice 6C handles `TECHNIQUE_RECOMMENDATION_MATRIX` separately. For every technique × SIL cell it
creates a source-scoped `TechniqueRecommendation` entity and links it with
`recommendsTechnique`, `hasIntegrityLevel`, and `hasRecommendationLevel`. Recommendation level is
a first-class `RecommendationLevel` entity, so `HR`, `R`, `—`, and `NR` remain semantic qualifiers
rather than being collapsed into `NormativeForce`. The row's local identifier and alternative
group plus deterministic IEC 61508-7 description and table-context references are retained as
literal assertions. Technique cells, SIL headers, recommendation markers, reference tokens, and
caption references all receive exact `Clause.plain_text` evidence anchors. These deterministic-only
ontology terms are declared by `functional-safety@2.1.0` but are intentionally absent from the LLM
source-extraction vocabulary.

Schemas are applied only when required normalized headers and non-empty row values are present.
Multi-level headers and row-spanning values are consumed from the T2 logical grid. An ambiguous
table remains `generic`; the implementation does not infer relations merely because cell values
look plausible.

## Separation from prose extraction

Table schema, recommendation level, and row relationships are structural/semantic dimensions of
the table itself and must not be inferred from the surrounding clause as narrative text. The
assertion-centred prose extractor therefore excludes `ClauseType.TABLE` and removes embedded table
payload from mixed-clause model input. Structured tables use the deterministic T2/T3 path instead.

Slice 6A reunifies the two paths at the proposal boundary: supported table relations become
`KnowledgeEntityProposal` and `NormativeAssertionProposal` values with exact cell-span evidence,
while prose assertions continue to use exact model evidence quotes. Slice 6B then unifies those
run-scoped proposals by normalized label plus compatible ontology type. Generic classes may refine
to one unambiguous subclass; incompatible siblings and ambiguous generic matches remain separate.
Equivalent same-clause assertions are rewritten to resolved entity IDs and may be deduplicated, but
source-clause boundaries are preserved. No proposal path writes canonical
`EngineeringDocument.knowledge` directly.

## Retrieval and IntelliDoc

The MCP adapter exposes tables and records directly. IntelliDoc-style retrieval now has an explicit T4 projection boundary. `RetrievalDocument`
values are generated reproducibly at table, row, concept, and relation granularity while
retaining stable source IDs back to T3 knowledge artifacts. Table projections request the
`structured-table-v1` tokenization profile so adapters can use a tokenizer different from
narrative clause indexing. Embedding chunks remain disposable index projections; the Knowledge
Base and its source evidence remain authoritative.

## Slice boundary

T1 captures identity and document structure only. T2 provides deterministic header
normalization, merged-cell reconstruction, row/column header paths, footnotes, units, reference
tokens, and canonical table normalization. T3 now maps `NormalizedTable` deterministically into
`KnowledgeTable`, `KnowledgeRecord`, and `StructuredKnowledgeRecord` artifacts. T4 now derives disposable retrieval documents at table, row, concept, and relation granularity.
Each projection declares a `structured-table-v1` tokenization profile; concrete tokenizers,
embedding models, vector stores, and GraphRAG implementations remain replaceable adapters.

## Current limitation

Projection and interpretation are implemented and covered by deterministic tests. Slice 6A
projects work-product, responsibility, traceability and verification-criteria matrices into
`DocumentKnowledgeProposal`; Slice 6B unifies prose/table runs and resolves document-local entities
without fuzzy matching; Slice 6C now projects qualified IEC 61508 technique recommendations through
the same proposal boundary without losing SIL/recommendation qualifiers. A dedicated assertion/table
qualification corpus and HITL review flow are introduced only after the unified proposal path is
complete. See
the [structured table corpus roadmap](../roadmap/structured-table-corpora.md).
