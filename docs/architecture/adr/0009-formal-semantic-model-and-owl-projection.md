# ADR 0009: Formal Semantic Model and OWL Projection

## Status
Accepted

## Goal alignment
The formal semantic layer turns accepted document knowledge into a **cross-document, cross-domain Engineering Knowledge Base**. `EngineeringDocument` remains the canonical representation of each source document and now owns accepted assertion-centred `DocumentKnowledge`; OWL remains a rebuildable machine-readable projection.

The separation is intentional: the **CBox describes interpretation context**, the **TBox/RBox defines domain semantics**, and the **ABox contains accepted assertions about represented engineering entities**.

## Context
Clause labels alone cannot express engineering entities, artifact dependencies, evidence relationships or the properties required for cross-domain reuse. At the same time, a graph projection must never become a second source of truth detached from the exact source clauses and review evidence.

## Decision
Formal semantics use versioned ontology resources and an explicit TBox/RBox/ABox/CBox separation under the namespace `http://lunetix.org/standards-atlas#`.

- **TBox/RBox**: versioned ontology classes and properties, including core and knowledge-domain extensions.
- **ABox**: assertions deterministically projected from accepted `EngineeringDocument.knowledge` entities and assertions plus structured deterministic knowledge.
- **CBox**: interpretation context derived from document structure, references, subject context, applicability, provenance and other accepted contextual facts. CBox assertions are context, not engineering-domain facts.
- Proposal runs, disagreements and rejected model outputs remain separate evaluation artifacts and do not enter the ABox merely because an extractor produced them.
- Every projected assertion retains links to its canonical `EvidenceAnchor`, originating clause and adoption provenance.
- Cross-document matching, equivalence and domain-transfer relations are derived views. They do not rewrite source-document assertions.
- The active formal ontology set is `standards-atlas-core@2.0.0` plus optional `functional-safety@2.0.0`. Core 2.0 models `EngineeringArtifact`/`WorkProduct`; evidence is expressed by `providesEvidenceFor`, not by an `EvidenceArtifact` class.
- Formal ontology descriptors expose an explicit source-extraction vocabulary. Technical structure, projection, CBox and provenance properties stay outside that view even though they remain valid formal terms.

The integrated formal projections form the Engineering Knowledge Base. RAG, GraphRAG, vector indexes and graph-query stores are replaceable serving adapters over canonical or formal projections. Chat, MCP, Doorstop, heatmaps and assurance workflows consume those layers; they do not define them.

## Refactoring transition
Slice 4B establishes canonical `DocumentKnowledge` projection as the only engineering ABox input. Canonical entities and predicates are validated against the exact formal ontology versions recorded by `DocumentKnowledge`; projected assertions retain evidence-anchor IDs, source-clause context, normative force and adoption provenance. The former proposal-to-ABox augmentation path has been removed.

`DocumentSemanticExtraction` remains temporarily as a proposal/qualification artifact only. Slice 5 replaces it with the assertion-centred `DocumentKnowledgeProposal` model and qualification boundary.

## Consequences
Formal reasoning, cross-standard artifact comparison and graph retrieval become possible without making OWL canonical. Evidence-backed `DocumentKnowledge` provides a stable adoption boundary between probabilistic extraction and formal projection, while the CBox/ABox distinction prevents interpretation context from being mistaken for domain knowledge.
