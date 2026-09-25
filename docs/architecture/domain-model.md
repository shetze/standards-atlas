# Domain model

## Canonical domain model

![Canonical domain model](diagrams/svg/canonical-domain-model-class-diagram.svg)

This UML class diagram is the detailed companion to the domain model described on this page. It focuses on stable architectural types and representative ownership relationships. Helper models, complete enum vocabularies, serialization schemas, validation internals, and specialized evaluation artifacts remain authoritative in code and in the topic-specific documents rather than being duplicated here.

A simplified domain-only orientation diagram remains available as `domain-model.svg` in the [diagram catalog](diagrams/README.md).

## Application boundary around the domain

![Application services, ports, and adapters](diagrams/svg/application-architecture-class-diagram.svg)

The application architecture is intentionally shown in a separate UML diagram. It identifies the principal application services, their outbound ports, and representative infrastructure adapters without mixing those dependencies into the canonical domain model. This separation mirrors the hexagonal architecture: domain types remain independent from storage, external SDKs, model providers, and runtime protocols.

## Canonical aggregate

`EngineeringDocument` is the canonical representation of one normalized standard, standard part, regulatory publication, or engineering document. It identifies the source document and owns an ordered clause hierarchy. Multi-part outputs are composed explicitly rather than by treating an export format as the aggregate.

A `Clause` contains a stable `ClauseId` and human-readable reference plus source/structure state:

- `ClauseBaseline` owns source-derived and deterministic facts: structured `ContentBlock` values, hierarchy, source token, structural profile/context, reference mentions and resolved reference relations, normative/structural classification, and optional publication attributes;
- `ClauseEnrichments` owns accepted clause-level interpretation context and contains only `ClauseApplicability`, `ContextRouting` and `ClauseSubjectContext`; engineering-domain meaning is represented as evidence-backed `DocumentKnowledge` assertions;
- `KnowledgeStateProvenance` records generated clause-context attributes that are not yet authoritatively confirmed.

At document level, `DocumentKnowledge` owns accepted engineering-domain knowledge as evidence-backed `KnowledgeEntity` and `NormativeAssertion` objects. Its `EvidenceAnchor`s point back to canonical clauses or bounded character ranges without duplicating protected source text. Assertions carry their own normative force and adoption provenance.

`baseline` describes the kind of processing, not certainty. A deterministic structural or reference result can remain `generated` until community-curated AtlasData confirms it. Plain text is derived from `baseline.content` through `render_content_as_plain_text`; it is not a second authoritative representation.

## Structured content

Content is represented by immutable blocks such as text, lists, tables, notes, pictures, formulas, and code. This preserves information needed for lossless normalization, readable exports, and later semantic analysis. Nested lists and table cells remain structured rather than being flattened prematurely. A `FormulaBlock` remains a formula even when semantic transcription is unavailable; in that state it may carry a PNG visual asset rendered from its source bounding box instead of being demoted to a generic `PictureBlock`.

Tables can additionally be projected into addressable `KnowledgeTable` and
`KnowledgeRecord` artefacts. These projections are deterministic views of the canonical
`TableBlock`; they are not a second persisted source of truth. A record preserves its
original cells and source evidence and may carry a conservative semantic interpretation.

## Structural profile and context

`StructuralProfile` describes independently determined structural dimensions, including canonical document section, domain category, annex status, and taxonomy provenance. `StructuralContext` materializes the surrounding graph evidence required by later processing: node/leaf role, ancestors, children, sibling position, predecessor/successor links, contextual ancestor content, structural reference edges, and structural scope mentions/edges that capture the reach of scope statements without interpreting their applicability semantics. Both are owned by the deterministic `TAXONOMY` stage.

A clause can therefore be located in a verification-oriented branch, inherit lifecycle context from headings, and occupy the last position of a sibling sequence without interpreting its statement-level meaning.

### StructuralContext and scope reach

![StructuralContext and scope reach](diagrams/svg/structural-context-scope-reach.svg)

`StructuralContext` is a materialized, structure-only graph view around one clause. Ancestors,
sibling position, child ids, contextual ancestor content, references, scope mentions, and
scope edges are all derived deterministically. `StructuralScopeMention` preserves the surface
signal and optional direction/cardinality hints; `StructuralScopeEdge` records the resolved or
deferred structural reach to target clauses.

Scope reach must not be confused with semantic applicability. A structural edge can tell the
ontology classifier that a statement structurally reaches the next sibling, a subtree, or the
current clause, but whether that statement expresses an applicability condition remains an
ontology decision.

## Assertion-centred semantic knowledge

The target semantic unit is an explicit engineering assertion, not a classification label for an entire clause. `DocumentKnowledge` schema 1 contains normalized entities, text-safe evidence anchors and subject/predicate/object assertions. Each assertion records assertion-local normative force and provenance, allowing one clause to contribute several independently qualified engineering statements.

`DocumentKnowledgeProposal` schema 1 is the separate non-canonical proposal aggregate used before qualification and adoption. It contains run and ontology identity, evidence anchors, `KnowledgeEntityProposal` and `NormativeAssertionProposal` values, non-fatal violations, terminal failures, retry attempts and extractor provenance. Derived proposal runs may additionally bind direct input proposals by run ID, SHA-256 content hash and original run provenance. Evidence grounding addresses a canonical clause **surface** rather than assuming that every semantic cue lives in `Clause.plain_text`: `EvidenceAnchor.source_clause_id` identifies the owning clause and `source_kind` selects `body` or `heading`; offsets and SHA-256 are relative to that exact surface. Entity proposals may use the local body, local heading, an ancestor heading, or a body/heading surface explicitly transported as associative structural context by assertion CBox 1.2. Associative context contains text-bearing ancestors and, for heading-only structural groups, the first earlier substantive descendant that introduces the group. Assertion evidence remains exact and local to the source clause body, so structural context can frame entity meaning without creating normative claims by itself. Missing or repeated quotes remain `unresolved_grounding` or `ambiguous_grounding` violations rather than silently widened evidence. `KnowledgeEntityProposal.proposal_clause_ids` retains which analyzed clause(s) produced a proposal even when its evidence is located on an ancestor heading. Assertions carry their own normative force and may target another proposed entity or a literal value. Confidence and rationale exist only on proposal records; accepted `KnowledgeEntity` and `NormativeAssertion` values deliberately do not inherit them. Proposal persistence is run-scoped and does not mutate `EngineeringDocument`.

`ClauseApplicability` is the minimal context contract for applicability: explicit presence plus optional `included`/`excluded` polarity. It is persisted as its own enrichment and projected as its own CBox context. Structural evidence, references and subject context stay separate from engineering-domain assertions. Clause-level statement, knowledge, process and role classification are not part of the canonical model.

## Evidence and provenance

`SourceEvidence` links knowledge back to physical source material through page and geometric anchors. Formula visual preservation consumes those anchors without changing their meaning. `ArtifactLineage` records how persisted artifacts derive from prior artifacts and deterministic transformations. `KnowledgeStateProvenance.generated_attributes` adds attribute-level authority tracking with a stable path, generator identity, generation method, and optional evidence references. Evidence belongs in the domain contract; adapter-specific parser objects do not.

## Assertion qualification contracts

Slice 7A introduces `AssertionGoldenSuite` schema 1 as the versioned truth contract used to measure
`DocumentKnowledgeProposal` quality. A suite is explicitly either `development` or `holdout`, binds
exact formal-ontology versions, and defines expected entities/assertions without reusing runtime
proposal IDs. Expected assertion evidence is represented as exact clause-local offsets plus SHA-256,
so protected source text is not copied into the golden contract.

`AssertionQualificationReport` schema 1 is metric-only. Entity and assertion matching is
deterministic and ID-independent; predicate, normative-force, grounding, and combined exact
assertion accuracy are reported separately. Proposal violations/failures remain visible as counts,
but Slice 7A does not translate metric values into canonical authority or adoption decisions.

Slice 7B adds `AssertionQualificationCascadeReport` as a separate non-canonical qualification
artifact. It records per-clause Efficient/Verify/Escalate routing, exact proposal-source hashes and
verifier decisions. It deliberately contains no accepted assertion set; canonical `DocumentKnowledge`
remains unchanged until the explicit Slice 8 adoption boundary.

Slice 7C adds `AssertionAutoAdoptionPolicy` and `AssertionAutoAdoptionReport` as non-canonical
qualification contracts. A policy carries explicit Development/Holdout thresholds; a report binds
those gates to exact golden-suite/report hashes, the production cascade/proposal hashes, and the
qualified Efficient runtime identity. Per-assertion decisions are eligibility only. They include the
source proposal/run, required entity IDs and evidence-anchor IDs needed by a later adoption service,
but they do not create `KnowledgeEntity`, `NormativeAssertion`, or `DocumentKnowledge` values.

## Table-derived knowledge

`KnowledgeTable` identifies one structured table within a clause and owns ordered
`KnowledgeRecord` rows. Stable IDs are derived from the document, clause, table position,
and row position. The table projection preserves captions, header cells, row and column
spans, source evidence, and a deterministic plain-text representation for later retrieval.

Known table kinds currently include generic tables, IEC 61508 technique-recommendation
matrices, and portable work-product, responsibility, verification-criteria, traceability,
and applicability matrices. `KnowledgeConcept` and `KnowledgeRelation` remain deterministic
T3 intermediates with exact source-column provenance. Slice 6A additionally projects the four
portable engineering relation kinds (work product, responsibility, traceability and verification
criteria) into the same non-canonical `DocumentKnowledgeProposal` entity/assertion contract used
by prose extraction. The deterministic table projector emits its own run-scoped proposal so its
provenance is not conflated with an LLM prose run. Slice 6B adds deterministic multi-source
unification: equal normalized labels merge only when their ontology classes form one unambiguous
subclass chain, aliases/evidence are unioned, and assertions are rewritten to the resolved entity
IDs. Incompatible sibling types and ambiguous generic matches remain separate. Table evidence is
bound to exact source-cell spans in canonical
`Clause.plain_text`; repeated labels are disambiguated structurally by table block and logical
row/column coordinates. Applicability remains outside engineering ABox projection. Slice 6C
projects IEC 61508 technique matrices without flattening their qualifiers: one reified
`TechniqueRecommendation` entity represents each technique × SIL statement and links to the
technique, `SafetyIntegrityLevel`, and normalized `RecommendationLevel`. Local identifiers,
alternative groups, IEC 61508-7 description references, and table-context references remain
source-bound literal assertions. `HR`/`R`/`—`/`NR` are recommendation levels and are not
misrepresented as assertion `NormativeForce`. Unrecognized or ambiguous tables remain generic
rather than receiving guessed semantics.

See [Table semantics](table-semantics.md) for the projection and evaluation boundaries.

## Knowledge extension points

`ClauseAnnotation` adds reviewed or generated explanatory knowledge with explicit visibility. `Relation` and semantic relation objects connect clauses and documents. These types are the basis for the planned cross-standard relationship graph. Candidate model runs and qualification proposals remain external evaluation artifacts; once accepted, engineering-domain knowledge is adopted into `DocumentKnowledge` with evidence anchors and provenance. Clause enrichments are reserved for interpretation context.

## Relationship to application architecture

The separate application-architecture class diagram shows representative application services consuming ports implemented by infrastructure adapters. It makes the boundary around the canonical model explicit without coupling the domain view to infrastructure details. It is not a complete service inventory: evaluation, semantic qualification, MCP transport, LLM runtime management, AtlasData lifecycle services, and specialized workflow helpers are covered by their own architecture documents and diagrams.

## Model rules

- Identifiers are explicit value objects.
- Domain models are immutable Pydantic models where practical.
- Export-specific metadata is isolated and optional.
- Internal references resolve against known clauses before Markdown publication.
- Structural dimensions and inherited context are materialized only by the deterministic taxonomy stage.
- Accepted engineering assertions are evidence-backed and adopted explicitly; proposal runs never become canonical merely because an analyzer emitted them.
- No domain model depends on storage paths or external SDK types.


## Formal semantic and context projection

`EngineeringDocument` remains canonical. Formal semantics are represented as a rebuildable `FormalSemanticProjection` containing provider-neutral TBox, RBox, ABox, and CBox assertions. ABox facts are projected from accepted `DocumentKnowledge`; CBox facts describe interpretation context sourced from structure, references, applicability and provenance. Projection never copies protected clause body text.

The stable Standards Atlas namespace is `http://lunetix.org/standards-atlas#` with prefix `stat`. No RDF framework, graph database, or GraphRAG implementation is part of the domain model. See [Formal Semantic & Context Model](formal-semantic-context-model.md).

## Engineering knowledge ontology

Ontology classes and predicates type `KnowledgeEntity` objects and `NormativeAssertion` relations. Canonical knowledge records the exact formal ontology versions used for those terms; projection rejects undeclared classes or predicates. Artifact/evidence semantics are relational: an engineering artifact may `providesEvidenceFor` a claim without becoming an intrinsic `EvidenceArtifact` kind. Artifact contracts, cross-domain matching and qualification cases are downstream views planned on top of accepted assertions rather than additional clause-classification dimensions.
