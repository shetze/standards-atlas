# ADR 0078: Qualify ontology-guided semantic extraction in qualification runs

## Status

Accepted

## Context

Slice 4 introduced ontology-guided entity and local-relation extraction as a rebuildable artifact. The existing semantic qualification matrix did not evaluate these outputs, so graph quality could not be separated from later retrieval quality.

## Decision

Qualification manifests may enable `semantic_extraction_qualification`. The workflow then executes an explicit semantic-extraction qualification step after the existing semantic qualification matrix.

The step evaluates persisted `DocumentSemanticExtraction` artifacts against the selected formal ontology versions. Ontology conformance and confidence gates are always measurable. Entity and relation precision/recall/F1 are reported only when a published gold file is configured; absent gold remains explicitly unscored.

The task is registered as `formal-semantic-knowledge-extraction/1.0.0`. Cross-domain mapping remains outside this task and outside Slice 4b.

This step does not couple the qualification domain to RDF stores, GraphRAG, Neo4j, or another retrieval implementation.

## Consequences

- qualification runs expose graph-input quality before hybrid retrieval is evaluated;
- ontology violations fail independently of textual classification consensus;
- missing gold data cannot masquerade as a zero or perfect score;
- a focused HITL gold corpus can be added incrementally without changing the extraction artifact contract.
