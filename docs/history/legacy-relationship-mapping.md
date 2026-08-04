# Legacy relationship-mapping prototype

> **Status: Historical.** This document describes the original IntelliDoc proof of concept. It is retained as design input for the current [IntelliDoc refactoring roadmap](../roadmap/intellidoc-refactoring.md), not as a reference for the present architecture or supported runtime.

## Goal

The prototype explored meaningful relationships between clauses from standards in different knowledge domains. Numbered clauses and subclauses were used as the comparison granularity, including their parent and sibling structure.

The intended result was an orientation aid rather than an authoritative equivalence mapping. Cross-domain standards contain both shared concerns and genuinely domain-specific requirements, so a relationship could be useful without representing identity or substitutability.

## Experimental approach

The prototype:

1. split standards into clauses;
2. vectorized clause content with an embedding model;
3. retrieved candidates from another domain;
4. adjusted ranking using sentence significance and available clause classifications;
5. inspected the resulting relationships using structural heuristics.

## Evaluation heuristics

### Self-identification

When searching inside the source domain, a clause should normally retrieve itself or an intentionally identical clause. This acted as a basic check of embedding and retrieval quality.

### Sibling clusters

Related source siblings should often map to related target siblings. Cluster continuity was treated as stronger evidence than isolated textual similarity.

### Reciprocity

A strong relationship discovered from domain A to domain B should often also appear when searching from B to A. Reciprocal retrieval was treated as an additional quality signal.

These heuristics were useful exploratory indicators, not sufficient qualification metrics.

## Prototype implementation choices

The historical implementation used choices such as:

- `nomic-embed-text` embeddings;
- NLTK sentence tokenization;
- sentence-level significance weighting;
- top-k retrieval;
- optional clause-type weighting;
- Ollama as the local model service;
- LlamaIndex as the retrieval framework.

These dependencies and heuristics are not architectural commitments of the refactored system.

## Lessons carried forward

The prototype established several requirements that remain relevant:

- relationships need explicit evidence and provenance;
- retrieval results must be evaluated rather than accepted as truth;
- structural context can improve relationship assessment;
- one-way similarity is weaker than reciprocal or clustered evidence;
- relationship discovery must remain adapter- and model-independent at the application boundary.

The target architecture and implementable steps are maintained in the [IntelliDoc refactoring roadmap](../roadmap/intellidoc-refactoring.md).
