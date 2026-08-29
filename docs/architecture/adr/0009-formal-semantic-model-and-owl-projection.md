# ADR 0009: Formal Semantic Model and OWL Projection

## Status
Accepted

## Goal alignment
The formal semantic layer turns document-centered evidence into a **cross-document, cross-domain Engineering Knowledge Base**. OWL is the machine-readable knowledge representation, while `EngineeringDocument` remains the canonical representation of each source document.

The separation is intentional: the **CBox describes interpretation context**, the **TBox/RBox defines domain semantics**, and the **ABox contains assertions about the represented engineering domain**. RAG, GraphRAG, graph queries, Chat, and MCP consume or expose this knowledge; they do not define it.

## Context
Classification labels alone cannot express cross-standard concepts, relations, contextual assertions, or graph reasoning. Standards Atlas needs a formal semantic layer without replacing canonical evidence.

## Decision
Formal semantics use versioned OWL resources and an explicit TBox/RBox/ABox/CBox separation under the namespace `http://lunetix.org/standards-atlas#`.

- **TBox/RBox**: versioned ontology classes and properties, including core and knowledge-domain extensions.
- **ABox**: qualified assertions about engineering-domain entities and relations projected from canonical documents and structured semantic artifacts.
- **CBox**: assertions describing the interpretation context of document fragments, including knowledge domain, deterministic taxonomy, accepted abstract semantic functions/profile context, provenance, and interpretation scope. CBox assertions are context, not domain facts.
- Deterministic facts are projected deterministically.
- Inferred concepts and relations are stored in a separate `DocumentSemanticExtraction`-style artifact with extraction provenance and are projected only as qualified/inferred assertions.
- `EngineeringDocument` remains canonical; OWL graphs are rebuildable semantic projections.

The integrated formal projections form the **Engineering Knowledge Base**: a knowledge-centered view that may span documents, standard families, and engineering domains while preserving links to canonical evidence.

RAG, GraphRAG, vector indexes, and graph-query stores are retrieval/serving adapters over canonical or formal projections and are replaceable. Chat, MCP, Doorstop, heatmaps, and other consumers remain interfaces or applications over these layers.

## Consequences
Formal reasoning, cross-standard comparison, and graph retrieval become possible without turning the OWL graph into a second canonical document representation. The explicit CBox/ABox boundary prevents interpretation context from being mistaken for domain knowledge, and provenance keeps integrated assertions traceable to their source clauses.
