# ADR 0074: Introduce a formal semantic and context model

## Status

Accepted.

## Context

Standards Atlas must discover and assess relationships between Functional Safety standards from different domains. The previous IntelliDoc prototype primarily embedded clause text and retrieved nearest clauses. The current refactoring already provides richer deterministic and classified information through Knowledge Domains, structural taxonomies, semantic dimensions, role relations, resolved references, structured knowledge records, and lineage.

The existing `application.ontology` package represents versioned controlled semantic dimensions and LLM-assisted classification. It is useful production machinery, but it is not an OWL TBox and should not be expanded until it ambiguously mixes classification vocabularies with formal ontology axioms.

Cross-domain semantics also depends on context. Knowledge Domain, structural location, applicability, taxonomy version, and provenance can determine whether two otherwise similar assertions are comparable. A TBox/ABox-only target would either lose this context or force it into ad-hoc metadata.

## Decision

Introduce a provider-neutral Formal Semantic & Context Model with four logical partitions:

- **TBox** for classes and concept axioms;
- **RBox** for relation/property axioms;
- **ABox** for concrete standards knowledge and instance assertions;
- **CBox** for semantic, structural, and epistemic context that qualifies assertions.

`CBox` is a Standards Atlas architectural convention. It does not claim to extend the OWL specification.

The canonical namespace is `http://lunetix.org/standards-atlas#` with prefix `stat`.

`EngineeringDocument` remains the canonical representation. Formal semantic graphs are rebuildable derived projections. Slice 1 introduces domain contracts and ports only; it deliberately avoids an RDF framework, graph database, OWL reasoner, SHACL engine, or GraphRAG dependency.

Knowledge Domains and taxonomy outputs are projected into CBox context rather than duplicated into the formal TBox. TBox/RBox axioms cannot depend on instance context frames. ABox/CBox assertions may reference explicit context frames and evidence identifiers.

Graph and vector retrieval remain replaceable outbound adapter concerns. GraphRAG may later implement a retrieval port, but it is not part of the domain model.

## Consequences

Formal semantics can evolve independently from storage/query technology. Existing taxonomy and ontology-classification stages retain their responsibilities. Cross-domain retrieval can use domain and structural context without declaring unsafe logical equivalence. Derived graph representations can be regenerated when projection rules change.

The architecture gains an additional model that must be versioned and qualified. Later slices must define the actual OWL vocabulary, RDF projection rules, validation shapes, provenance mapping, and cross-domain mapping semantics without collapsing reviewed relationships into inferred ontology axioms.

## Follow-up

1. Define the Standards Atlas core TBox/RBox and a small Functional Safety upper ontology.
2. Implement deterministic projection from `EngineeringDocument` and existing context sources.
3. Add RDF serialization and validation adapters behind the new ports.
4. Qualify cross-domain concept alignment on a bounded corpus before adding graph-assisted retrieval.
5. Add graph/vector/hybrid retrievers only behind the existing relationship candidate boundary.
