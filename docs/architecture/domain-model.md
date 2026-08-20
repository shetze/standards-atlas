# Domain model

![Current architecture class diagram](diagrams/svg/current-architecture-class-diagram.svg)

The multi-view UML diagram contains the canonical domain model and a second view of principal application services, ports, and infrastructure adapters. The first view is the detailed companion to this document. It deliberately focuses on stable architectural types and representative relationships; helper models, all enum values, serialization schemas, validation internals, and every specialized application artifact are documented in code and in the topic-specific documents rather than duplicated in the class diagram.

A simplified domain-only orientation diagram remains available as `domain-model.svg` in the [diagram catalog](diagrams/README.md).

## Canonical aggregate

`EngineeringDocument` is the canonical representation of one normalized standard, standard part, regulatory publication, or engineering document. It identifies the source document and owns an ordered clause hierarchy. Multi-part outputs are composed explicitly rather than by treating an export format as the aggregate.

A `Clause` contains:

- a stable `ClauseId` and human-readable reference;
- structured `ContentBlock` values instead of a single text field;
- parent/child structure and clause type;
- source evidence such as page anchors and bounding boxes;
- a multi-dimensional `StructuralProfile` and materialized `StructuralContext`;
- ontology-owned `SemanticClassification` results and semantic relations;
- annotations and relations;
- optional Doorstop projection attributes.

Plain text is derived from structured content through `render_content_as_plain_text`; it is not a second authoritative representation.

## Structured content

Content is represented by immutable blocks such as text, lists, tables, notes, pictures, formulas, and code. This preserves information needed for lossless normalization, readable exports, and later semantic analysis. Nested lists and table cells remain structured rather than being flattened prematurely. A `FormulaBlock` remains a formula even when semantic transcription is unavailable; in that state it may carry a PNG visual asset rendered from its source bounding box instead of being demoted to a generic `PictureBlock`.

Tables can additionally be projected into addressable `KnowledgeTable` and
`KnowledgeRecord` artefacts. These projections are deterministic views of the canonical
`TableBlock`; they are not a second persisted source of truth. A record preserves its
original cells and source evidence and may carry a conservative semantic interpretation.

## Structural profile and context

`StructuralProfile` describes independently determined structural dimensions, including canonical document section, domain category, annex status, and taxonomy provenance. `StructuralContext` materializes the surrounding graph evidence required by later processing: node/leaf role, ancestors, children, sibling position, predecessor/successor links, contextual ancestor content, structural reference edges, and structural scope mentions/edges that capture the reach of scope statements without interpreting their applicability semantics. Both are owned by the deterministic `TAXONOMY` stage.

A clause can therefore be located in a verification-oriented branch, inherit lifecycle context from headings, and occupy the last position of a sibling sequence without interpreting its statement-level meaning.

## Semantic classification

`SemanticClassification` stores ontology results and semantic relations separately from document structure. Automatic assignment of statement functions, knowledge kinds, process functions, applicability functions, and responsibility functions is owned exclusively by the `ONTOLOGY` stage. Structural evidence is supplied through `StructuralProfile` and `StructuralContext`; it is evidence for ontology classification, not semantic truth. Some legacy structural compatibility fields remain in the persisted model until a later schema migration, but no active classifier derives ontology values outside `ONTOLOGY`.

## Evidence and provenance

`SourceEvidence` links knowledge back to physical source material through page and geometric anchors. Formula visual preservation consumes those anchors without changing their meaning. `ArtifactLineage` records how persisted artifacts derive from prior artifacts and deterministic transformations. Evidence belongs in the domain contract; adapter-specific parser objects do not.

## Table-derived knowledge

`KnowledgeTable` identifies one structured table within a clause and owns ordered
`KnowledgeRecord` rows. Stable IDs are derived from the document, clause, table position,
and row position. The table projection preserves captions, header cells, row and column
spans, source evidence, and a deterministic plain-text representation for later retrieval.

Known table kinds currently include generic tables, IEC 61508 technique-recommendation
matrices, and portable work-product, responsibility, verification-criteria, traceability,
and applicability matrices. Portable interpretations use `KnowledgeConcept` and
`KnowledgeRelation` values with exact source-column provenance. IEC 61508 interpretations
add SIL-qualified recommendation levels and resolved clause references. Unrecognized or
ambiguous tables remain generic rather than receiving guessed semantics.

See [Table semantics](table-semantics.md) for the projection and evaluation boundaries.

## Knowledge extension points

`ClauseAnnotation` adds reviewed or generated explanatory knowledge with explicit visibility. `Relation` and semantic relation objects connect clauses and documents. These types are the basis for the planned cross-standard relationship graph. Model-generated proposals remain external evaluation artifacts until accepted and published into canonical data.

## Relationship to application architecture

The second page of the UML class diagram shows representative application services consuming ports implemented by infrastructure adapters. It is included to make the boundary around the canonical model explicit. It is not a complete service inventory: evaluation, semantic qualification, MCP transport, LLM runtime management, AtlasData lifecycle services, and several specialized workflow helpers are covered by their own architecture documents and diagrams.

## Model rules

- Identifiers are explicit value objects.
- Domain models are immutable Pydantic models where practical.
- Export-specific metadata is isolated and optional.
- Internal references resolve against known clauses before Markdown publication.
- Structural dimensions and inherited context are materialized only by the deterministic taxonomy stage.
- Automatic ontology dimensions are assigned only by the ontology stage or imported as explicit reviewed/public annotations.
- No domain model depends on storage paths or external SDK types.

## Engineering knowledge ontology

`SemanticClassification.knowledge_kinds` identifies what engineering knowledge a clause
represents independently from how the statement is phrased. The central vocabulary is
`technique`, `measure`, `method`, `process`, `artifact`, `role`, `evidence`, and `concept`.
For example, a clause can simultaneously be an informative `description` and a
`technique`. Domain-specific refinements remain in versioned `domain_functions`.
