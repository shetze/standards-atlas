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

## Knowledge domain and hierarchy

A **knowledge domain** groups standards and relationships for a field such as functional safety. A configured hierarchy determines composed Doorstop publication, while the filesystem remains an implementation detail.

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
