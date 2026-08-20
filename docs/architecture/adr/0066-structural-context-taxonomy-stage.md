# ADR 0066: Materialize structural context in a dedicated taxonomy stage

## Status

Accepted

## Context

Engineering standards encode meaning in document structure before individual clauses are interpreted semantically. Headings, ancestor paths, sibling order, node-local introductory content, and references between clauses all provide deterministic evidence that should be available to later ontology classification.

## Decision

The document workflow contains a dedicated `TAXONOMY` stage after content enrichment. The stage materializes a `StructuralContext` for every clause without performing LLM-based semantic interpretation.

A structural context records:

- whether a clause is a structural node or a leaf;
- the complete ancestor path and headings;
- child identifiers;
- sibling index/count plus first/last and predecessor/successor relations;
- ancestor clauses whose own content can provide context for descendants; and
- structural reference edges projected from persisted `ReferenceMention` evidence.

Structural context is stored on the `Clause` so ontology classification can consume it directly. Reference mentions remain the source evidence; the taxonomy stage does not re-parse reference text.

## Consequences

Ontology processing can use a deterministic, explainable context graph rather than reconstructing hierarchy from flat clauses. Node content is referenced rather than copied into descendants. Unresolved reference mentions remain visible as structural edges with their resolution status.
