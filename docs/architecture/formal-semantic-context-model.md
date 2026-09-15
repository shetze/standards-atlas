# Formal Semantic & Context Model

## Purpose

Standards Atlas uses a formal semantic layer to represent reusable engineering meaning across standards and Knowledge Domains without replacing `EngineeringDocument` as the canonical document representation. The semantic layer is a derived projection and is independent from a concrete RDF library, graph database, query engine, vector store, or GraphRAG implementation.

The stable Standards Atlas namespace is:

```turtle
@prefix stat: <http://lunetix.org/standards-atlas#> .
```

## Logical partitions

The model distinguishes four logical boxes.

| Box | Responsibility | Examples |
|---|---|---|
| **TBox** | Concept and class semantics | `stat:Clause`, `stat:VerificationActivity`, subclass axioms |
| **RBox** | Relation/property semantics | `stat:requires`, `stat:performedBy`, inverse/property-chain axioms |
| **ABox** | Concrete standards knowledge | a specific clause, requirement, activity, artifact, role, or assertion |
| **CBox** | Context that qualifies assertions | Knowledge Domain, taxonomy result, structural position, applicability, provenance |

`CBox` is a Standards Atlas architectural convention rather than an OWL language construct. It makes context a first-class part of the domain contract while leaving the eventual RDF representation open.

## Context dimensions

A context frame groups facets from three independent sources:

- **semantic context**: Knowledge Domains, domain functions, applicability, deterministic primary subject, lifecycle or integrity-level interpretation;
- **structural context**: document identity, parent/ancestor hierarchy, sibling position, node/leaf status, scope reach, resolved references;
- **epistemic context**: taxonomy/ontology versions, extraction or classification source, model or rule identity, confidence, qualification and review provenance.

Context is not copied into the TBox. Taxonomies remain the deterministic or classified sources of context; the CBox is their formal semantic projection.

## Canonical versus derived data

`EngineeringDocument` remains the source of truth for clause structure and content. Formal semantic data is derived:

```text
EngineeringDocument
      +
Knowledge Domain selections
      +
Taxonomy / semantic annotations
      +
Lineage and qualification evidence
      |
      v
FormalSemanticProjection
  TBox / RBox references
  ABox assertions
  CBox context frames
```

A projection may be rebuilt when ontology, taxonomy, or projection logic changes. It must therefore carry stable source identifiers and must not become the only storage location for protected clause content.

## Provider-neutral domain contracts

`standards_atlas.domain.model.formal_semantics` defines the Slice-1 contracts:

- `SemanticResource` for stable IRI-compatible identifiers;
- `SemanticLiteral` for typed or language-qualified literal values;
- `SemanticBox` for TBox/RBox/ABox/CBox partitioning;
- `ContextKind`, `ContextFacet`, and `ContextFrame` for explicit context;
- `FormalAssertion` for provider-neutral subject/predicate/object statements;
- `FormalSemanticProjection` for the derived document-level projection.

The contracts intentionally do not import RDFLib, OWL APIs, SPARQL clients, graph databases, or GraphRAG frameworks.

## Projection boundary

`FormalSemanticProjector` is the application port that turns canonical documents and selected Knowledge Domains into a formal projection. `FormalSemanticProjectionRepository` is the persistence port for derived projections.

Concrete adapters may later serialize the same projection as RDF/Turtle, JSON-LD, named graphs, RDF-star, a property graph, or another representation. Selection of one representation must not leak into the domain contracts.

## Relationship discovery boundary

Formal semantics and retrieval remain separate concerns. Relationship candidate retrieval consumes semantic/context projections but is not part of the TBox/RBox/ABox/CBox model.

Potential implementations remain replaceable behind retrieval ports:

```text
RelationshipCandidateRetriever
    |- lexical adapter
    |- vector adapter
    |- graph traversal adapter
    |- GraphRAG adapter
    `- hybrid adapter
```

GraphRAG is therefore an optional adapter strategy, not an architectural dependency or domain concept.

## Context and cross-domain mapping

Knowledge Domains are both addressable knowledge objects and interpretation contexts. A concept used in railway functional safety and a similarly named concept used in automotive functional safety must not be promoted automatically to OWL equivalence. Cross-domain alignment is an evidence-backed relationship problem and may later use SKOS-style mappings or Standards Atlas relationship assertions.

The CBox allows candidate retrieval and assessment to distinguish assertions that are structurally or lexically similar but differ in domain, scope, integrity level, lifecycle phase, normative status, or epistemic quality.

## Versioned formal ontologies

The active clean-break ontology set is packaged under `resources/formal_ontologies/`:

- `standards-atlas-core/2.0.0` defines standards/projection vocabulary plus the reusable Engineering Knowledge TBox/RBox;
- `functional-safety/2.0.0` imports Core 2.0 and adds the small Functional Safety extension.

Core 2.0 replaces the generic `Artifact`/`EvidenceArtifact` hierarchy with `EngineeringArtifact` and `WorkProduct`. `Specification`, `Plan`, `Report` and `EngineeringRecord` are work products. Evidence is relational: an artifact may `providesEvidenceFor` an engineering entity or claim without acquiring an intrinsic evidence-artifact type. The engineering RBox includes the small, reusable relation vocabulary `specifies`, `plans`, `records`, `reportsOn`, `producedBy`, `usedBy`, `derivedFrom`, `refines`, `implements`, `tracesTo`, `providesEvidenceFor`, `dependsOn`, `responsibleFor`, and related composition/applicability relations.

The formal ontology resource family is deliberately separate from `resources/ontologies/`, which holds controlled context vocabularies. A versioned YAML descriptor identifies each formal ontology resource without making an RDF framework a production dependency. The descriptor also declares an explicit `extraction_vocabulary`: only those classes and properties may be offered to source-text extractors. Structural RDF terms, CBox serialization properties and extraction-provenance properties remain valid formal vocabulary but are not exposed as engineering source-extraction candidates. Repository loading rejects extraction-view terms that are not declared by the accompanying Turtle.

The vocabulary namespace remains stable while ontology IRIs are versioned. Concrete standards and clauses are not embedded in these TBox/RBox resources. The pre-2.0 formal ontology resources were removed during the destructive refactoring window rather than retained as compatibility inputs.

## Slice boundaries

Slice 3 adds deterministic ABox/CBox projection from `EngineeringDocument`. The projection materializes only facts already present in the canonical document, including structure, references, applicability, subject context and lineage; it does not infer new engineering concepts and does not duplicate protected clause body text.

Slice 4A establishes Formal Ontology 2.0 and the explicit source-extraction vocabulary boundary. The current projection uses `standards-atlas-core@2.0.0` and, when Functional Safety context is present, `functional-safety@2.0.0`. The core CBox vocabulary includes deterministic `primarySubject`, `subjectConfidence`, and `subjectEvidenceKind` facets. A Turtle adapter emits direct RDF triples plus reified `stat:SemanticAssertion` and explicit context-facet resources. The provider-neutral projection can also be persisted as versioned JSON under `.atlas/data/formal-semantic-projections/`.

Slice 4B will project accepted `EngineeringDocument.knowledge` deterministically into the ABox and remove the remaining proposal-to-ABox augmentation path. Slice 5 will then replace the transitional `DocumentSemanticExtraction` contract with assertion-centred `DocumentKnowledgeProposal` extraction. Until that cut-over, the existing extractor is constrained to the explicit Ontology 2.0 extraction vocabulary; unknown or non-extractable classes/properties are rejected non-fatally and retained as qualification violations.

Qualification feedback may refine Ontology 2.0 during the destructive refactoring window. Engineering composition (`stat:hasPart` / `stat:partOf`) remains distinct from document containment (`stat:containsClause`), while source extractors receive only the explicit engineering extraction view. Undeclared or non-extractable model terms are not promoted into OWL merely because an extractor produced them.

Entity identity and response-local relation references are deliberately separated. The LLM returns an ordered entity array and relations refer to zero-based entity indexes; it does not generate persistent or response-local entity identifiers. The adapter derives stable `stat:` entity IRIs from document key, internal clause ID, normalized label, and ontology class. Extraction artifacts and qualification diagnostics retain both the stable internal clause ID and the human-readable standard clause reference (plus title when available).

Slice 4A still does **not** introduce:

- SHACL validation;
- a triple store or SPARQL service;
- graph indexing;
- GraphRAG;
- relationship candidate generation or cross-domain mapping.

Those capabilities remain incremental follow-up work behind the existing ports.

## Related documentation

- [Knowledge Domains](knowledge-domains.md)
- [Structural classification](structural-classification.md)
- [Relationship mapping](relationship-mapping.md)
- [Domain model](domain-model.md)
- [Ports and adapters](ports-and-adapters.md)
- [ADR 0009](adr/0009-formal-semantic-model-and-owl-projection.md)

## Qualification boundary

Ontology-guided concept and local-relation extraction is qualified as its own semantic task before relationship retrieval is evaluated. Qualification always measures conformance against the selected formal ontology vocabulary and confidence gates. Gold precision/recall/F1 is emitted only when a published extraction gold corpus is configured; otherwise these metrics remain explicitly unscored.

See [ADR 0012](adr/0012-semantic-qualification-and-evidence-model.md).
