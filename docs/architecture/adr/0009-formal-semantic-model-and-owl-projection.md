# ADR 0009: Formal Semantic Model and OWL Projection

## Status
Accepted

## Context
Classification labels alone cannot express cross-standard concepts, relations, contextual assertions, or graph reasoning. Standards Atlas needs a formal semantic layer without replacing canonical evidence.

## Decision
Formal semantics use versioned OWL resources and an explicit TBox/RBox/ABox/CBox separation under the namespace `http://lunetix.org/standards-atlas#`.

- **TBox/RBox**: versioned ontology classes and properties, including core and knowledge-domain extensions.
- **ABox**: assertions projected from canonical documents and structured semantic artifacts.
- **CBox**: context assertions describing knowledge domain, taxonomy/profile context, provenance, and interpretation scope.
- Deterministic facts are projected deterministically.
- Inferred concepts and relations are stored in a separate `DocumentSemanticExtraction`-style artifact with extraction provenance and are projected only as qualified/inferred assertions.
- `EngineeringDocument` remains canonical; OWL graphs are rebuildable semantic projections.

GraphRAG/retrieval stores are adapters over these projections and are replaceable.

## Consequences
Formal reasoning and graph retrieval become possible without contaminating canonical document evidence with model-dependent inference.
