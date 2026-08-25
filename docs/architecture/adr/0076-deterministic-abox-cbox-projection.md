# ADR 0076: Project EngineeringDocument deterministically into ABox/CBox

## Status

Accepted.

## Context

ADRs 0074 and 0075 established the provider-neutral formal semantic contracts and the versioned Standards Atlas core and Functional Safety ontologies. The remaining gap is a reproducible bridge from canonical `EngineeringDocument` data into concrete formal-semantic assertions and context.

The projection must preserve the existing architectural boundary: `EngineeringDocument` remains canonical, protected clause content must not be duplicated into graph artifacts, and RDF or graph-provider APIs must not leak into the application/domain model.

## Decision

Introduce `DeterministicFormalSemanticProjector` as the application implementation of `FormalSemanticProjector`.

The projector emits:

- ABox assertions for document/clause identity, containment, parent/sibling structure and already-resolved semantic relations;
- one CBox `ContextFrame` per clause containing Knowledge Domain, semantic-classification, applicability, normative, structural-profile/context and lineage facets;
- stable assertion, document, clause and context IRIs in the `http://lunetix.org/standards-atlas#` namespace;
- explicit projection and ontology version metadata so the derived artifact can be rebuilt deterministically.

The projector does not infer new concepts or engineering entities and does not copy canonical clause body text.

Add `standards-atlas-core` 1.1.0 and `functional-safety` 1.1.0. The new core version adds only vocabulary required to represent projected documents, reified assertions and context facets. Previous 1.0.0 resources remain unchanged and readable.

Add `FormalSemanticSerializer` as a provider-neutral port and a Turtle RDF adapter. The Turtle adapter emits both direct triples for graph querying and reified `stat:SemanticAssertion` resources so context/evidence remains attached to each assertion. Context facets are represented explicitly and retain facet kind, predicate, value and source.

Add a versioned filesystem repository for rebuildable `FormalSemanticProjection` JSON artifacts under `.atlas/data/formal-semantic-projections/`.

## Consequences

Standards Atlas now has a deterministic, inspectable semantic graph projection without adopting a triple store, SPARQL service, reasoner or GraphRAG framework. RDF remains an adapter representation, while the provider-neutral projection is suitable for other graph or retrieval adapters.

Changes in ontology or projection rules can regenerate graph artifacts from canonical documents. Cross-domain entity extraction and candidate retrieval remain separate later concerns.

## Follow-up

1. Add SHACL validation once projection invariants have stabilized on representative standards.
2. Extend extraction from classification context to explicit engineering concept/entity assertions.
3. Add graph/vector retrieval adapters behind relationship-candidate ports.
4. Qualify cross-domain relationship discovery with an ablation corpus.
