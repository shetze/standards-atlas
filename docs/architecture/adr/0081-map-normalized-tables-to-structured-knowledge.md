# ADR 0081: Map normalized tables into structured knowledge before retrieval

- Status: Accepted
- Date: 2026-08-26

## Context

T1 introduced first-class table identity and T2 introduced a deterministic, semantics-free
`NormalizedTable` projection. The existing `KnowledgeTableProjectionService` still interpreted raw
`TableBlock` content directly, which duplicated header/span handling and allowed table semantics to
bypass the canonical T2 normalization boundary.

Structured tables contain explicit schema signals in headers, row positions, recommendation
markers, and references. Reconstructing these relations with narrative LLM extraction would discard
available structure and make the result harder to reproduce and qualify.

## Decision

Standards Atlas introduces a deterministic `StructuredKnowledgeMappingService` as the T3 boundary.

- T3 accepts only `NormalizedTable` inputs for semantic table mapping.
- `KnowledgeTable`, `KnowledgeRecord`, `StructuredKnowledgeRecord`, `KnowledgeConcept`, and
  `KnowledgeRelation` remain rebuildable projections rather than persisted sources of truth.
- The historical `KnowledgeTableProjectionService` remains as a compatibility facade and always
  executes `TableBlock -> NormalizedTable -> StructuredKnowledgeMappingService` internally.
- The filesystem knowledge-table repository consumes the read-only normalized-table repository and
  applies T3 mapping; it does not reinterpret persisted `TableBlock` rows itself.
- Unknown or ambiguous table schemas remain `generic` and produce no invented concepts or
  relations.
- IEC 61508-3 recommendation matrices map each technique/measure and SIL column into explicit
  concepts. `recommended_for` relations retain the normalized recommendation level as a qualifier,
  while the existing `TechniqueRecommendation` projection remains available for compatibility.
- Portable header-driven mappings continue to support work-product, responsibility, traceability,
  verification-criteria, and applicability matrices, but now use normalized multi-level headers and
  logical span reconstruction from T2.
- `StructuredKnowledgeRecord` validates unique concept identifiers and requires every relation
  endpoint to reference a concept present in the same record.
- T3 performs no embedding, retrieval serialization, graph ranking, or LLM-based semantic guessing.
  Those concerns remain outside the mapping boundary; table retrieval projections belong to T4.

## Consequences

All table semantics now share one normalized structural input and therefore no longer need to
reimplement merged-cell or header reconstruction. IEC 61508 Annex A can be represented as many
small evidence-backed records rather than one narrative semantic-extraction request. Future graph
projection can consume stable structured concepts and relations while preserving row/column source
provenance.
