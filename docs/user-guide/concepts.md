# Core concepts

## Standard family and physical document

A **standard family** is the logical standard represented in the catalog. A family can contain several **physical source documents**, such as individual parts or editions. Physical documents retain their own provenance and page selection.

## Extracted and normalized documents

The **extracted document** is Docling-native source evidence. The **normalized document** is a deterministic and lossless representation used by subsequent stages. Normalization records transformations rather than silently rewriting content.

## AtlasData and alignment

**AtlasData** is the reviewable public structural baseline: identifiers, headings, clause types and copyright-safe annotations. **Alignment** maps references detected in normalized source content to that baseline. Automatic alignment is a proposal until a reviewer accepts or overrides it.

## EngineeringDocument and Clause

`EngineeringDocument` is the canonical domain representation. A `Clause` contains structured `content`, source evidence, references, annotations and an optional multi-dimensional `StructuralProfile`. The former one-dimensional `SemanticRole` and `Clause.semantic_roles` model no longer exists.

## KnowledgeTable and KnowledgeRecord

A `KnowledgeTable` is an addressable projection of one structured table embedded in a
clause. A `KnowledgeRecord` represents one logical row and preserves its cells, headers,
spans, source evidence, and stable identity. Supported table schemas may add normalized
concepts and relations, but the original `TableBlock` remains authoritative.

Table semantics are intentionally separate from clause statement functions. A
responsibility matrix can contain `responsible_for` relations without turning the
surrounding clause into a `responsibility_assignment`.

## StructuralProfile

A structural profile classifies independent dimensions instead of forcing a clause into one role. Dimensions can describe, for example, normative status, statement function, lifecycle context, evidence relevance or document region. Taxonomies are knowledge-domain specific and must not be inferred from keywords alone when evidence is insufficient.

## Subject candidate vocabulary

AtlasData term headings provide the initial open vocabulary for clause subjects. Standards
Atlas derives this vocabulary deterministically from `ClauseType.TERM` entries, preserves
each original label and source reference, and merges only lexical variants under conservative
normalization. The resulting candidates are not CBox assertions. A separate deterministic
subject-identification stage selects at most one `primary_subject` for each clause. It prefers
matches in the clause heading and text, then inherits the nearest matching ancestor heading, and
finally considers resolved scope context. Every result records its evidence source and a
deterministic confidence. Equally specific matches remain explicit ambiguities instead of being
broken by an arbitrary lexical tie-break. Unresolved clauses remain explicit rather than receiving
an invented subject. CBox projection is a later stage, so the identification heuristic can be
qualified before it becomes interpretation context.

## CBox, TBox, and ABox

Standards Atlas uses OWL for formal engineering knowledge while keeping `EngineeringDocument` canonical. A domain-specific **TBox** defines domain concepts, relations, and constraints. The **CBox** is the Standards Atlas interpretation context for a document fragment: it combines Knowledge Domain, deterministic taxonomy, semantic functions, structural position, source identity, provenance, and qualification evidence. It describes how a clause is to be interpreted rather than asserting the clause's engineering-domain knowledge itself.

Using clause content plus that context, formal semantic extraction derives an **ABox** containing assertions about concrete activities, artifacts, roles, hazards, techniques, and other domain individuals. Context and domain knowledge therefore remain separate even when they originate from the same clause. Every ABox assertion must retain enough provenance to be traced back through its extraction and qualification evidence to that clause and its source.

## Knowledge domain and hierarchy

A **knowledge domain** groups standards and relationships for a field such as functional safety and selects the semantic context in which clauses are interpreted. A configured hierarchy determines composed publication views such as Doorstop, while the filesystem remains an implementation detail.

## Engineering knowledge base

Clause-level formal projections accumulate into a knowledge-centric view across EngineeringDocuments. Shared or mapped domain semantics allow concepts and assertions from independently authored standards and different engineering domains to be related without collapsing their source identity. The knowledge base complements the document-centric `EngineeringDocument` view; it does not replace it.

## Retrieval and access

Enriched EngineeringDocuments and formal semantic projections can feed lexical, vector, RAG, and GraphRAG indexes or graph-query services. These structures form a derived retrieval and serving layer rather than canonical storage. Interactive chat, MCP clients, Doorstop traces, relationship analysis, heatmaps, and future applications consume this layer and can be changed without redefining the knowledge model.

## Qualified semantic analysis

LLMs are one implementation technique for semantic tasks that cannot be derived reliably by deterministic processing. Their outputs are accepted only through explicit, qualified semantic contracts and remain subject to provenance and review rules. The architecture permits other analyzers to implement the same contracts, so the project is not coupled conceptually to a particular LLM or inference technique.

## Review gate

A **review gate** is an intentional workflow pause. Standards Atlas preserves uncertainty and requires a human decision rather than publishing weak extraction or alignment as authoritative data.

## Role relations and RACI

Role semantics are represented as relations rather than a clause-level responsibility
label. Role processing is presence-first. `role_semantics_present` records explicit role or
responsibility semantics even when a complete relation cannot be extracted; for example,
"the analysis shall be verified" is role-semantic without identifying the verifier. A
grounded relation identifies an `actor`, a controlled `relation`, a `target`, and optionally
a `condition` plus evidence. This preserves distinctions such as `performs`,
`verifies`, `independent_of`, and `assumes_role` that cannot be represented safely by the
former responsibility taxonomy.

RACI is a projection over these relations, not a primary ontology. For example,
`performs` can support a Responsible view when appropriate, while Accountable, Consulted,
and Informed are emitted only from explicit evidence; they are never inferred merely
because a role performs an activity.
