# ADR 0075: Introduce versioned core and Functional Safety ontologies

## Status

Accepted.

## Context

ADR 0074 introduced provider-neutral TBox/RBox/ABox/CBox contracts and established `http://lunetix.org/standards-atlas#` as the stable `stat:` namespace. The next step requires an actual formal vocabulary before document knowledge can be projected into an ABox.

The existing `resources/ontologies/**/ontology.yaml` resources remain controlled vocabularies for production semantic classification. Reusing that resource family for OWL would conflate classification dimensions with formal ontology axioms.

## Decision

Introduce a separate, versioned `resources/formal_ontologies/` family.

`standards-atlas-core` defines domain-independent standards and engineering concepts such as standards, clauses, semantic assertions, context frames, Knowledge Domains, processes, activities, artifacts, evidence, roles, techniques/measures, system entities and integrity levels, together with a conservative base relation vocabulary.

`functional-safety` imports the core ontology and defines a small Functional Safety upper ontology for safety lifecycle concepts, assurance activities, verification, validation, assessment, safety evidence, safety roles, techniques/measures and safety integrity levels.

Both ontologies use the stable namespace `http://lunetix.org/standards-atlas#` with prefix `stat`. Their ontology/version IRIs are version-specific and distinct from the stable vocabulary namespace.

Formal ontology metadata is loaded through a provider-neutral packaged-resource repository. No RDF parser, OWL reasoner, triple store, SPARQL engine or GraphRAG dependency is introduced into production code in this slice.

The formal ontology contains TBox/RBox vocabulary only. Concrete standards, clauses and extracted assertions remain ABox data to be generated in Slice 3. Knowledge-Domain and taxonomy-derived context remains CBox data and is not hard-coded as standard-specific ontology individuals.

## Consequences

The project gains a stable vocabulary against which deterministic projection rules can be implemented and qualified. Classification ontologies and formal OWL ontologies remain separate resource families with separate lifecycle and schema contracts.

The initial vocabulary is intentionally small. Domain-specific terms should only be promoted into the formal ontology when they are reusable semantic concepts rather than observations about one particular standard.

## Follow-up

1. Implement deterministic ABox/CBox projection from `EngineeringDocument`, Knowledge Domains, taxonomy results and semantic annotations.
2. Add RDF serialization and validation adapters behind provider-neutral ports.
3. Add SHACL shapes once concrete projection invariants are known.
4. Qualify vocabulary mappings and cross-domain concept alignment before graph-assisted relationship retrieval.
