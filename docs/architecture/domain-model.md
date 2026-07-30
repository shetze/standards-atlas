# Domain model

![Domain model](diagrams/svg/domain-model.svg)

`EngineeringDocument` is the canonical aggregate. It is identified by a
`DocumentKey` and contains ordered `Clause` objects together with document
metadata, annotations, and artifact lineage. The model is intentionally broader
than a standard and can also represent specifications, reports, safety-case
artifacts, and other structured engineering documents.

## Clauses and structured content

A `Clause` carries a stable identifier, standard reference, clause type, title,
ordered structured content, hierarchy information, adapter-neutral export
attributes, and semantic classification. Content blocks distinguish paragraphs,
lists, tables, figures, formulas, and other material rather than flattening the
protected source into Markdown.

The `plain_text` property is a deterministic projection of the structured
content. It is used for search and evaluation, but it is not a second canonical
content representation.

## SemanticClassification

Every clause contains a `SemanticClassification`. It replaces the former flat
`semantic_roles` vocabulary with independent dimensions:

- `statement_functions` for requirement, recommendation, permission,
  prohibition, definition, description, rationale, example, note, and related
  statement functions;
- `applicability_functions` for scope, conditions, inclusions, exclusions, and
  exceptions;
- `responsibility_functions` for assignments, exclusions, and role conditions;
- `document_structure`, qualified by a document-family taxonomy;
- `normative_status`;
- versioned `domain_functions` owned by a `KnowledgeDomain` taxonomy;
- resolved internal and external semantic relations.

The dimensions are intentionally orthogonal. A clause can, for example, be a
normative requirement, allocate responsibility, belong to a document-family
section, and participate in external relations at the same time. Taxonomy-owned
strings remain namespaced and versioned so new domains do not require expansion
of a central enum.

## StructuralProfile

`StructuralProfile` is a separate domain contract for multidimensional
structural classification. It contains:

- a broad `canonical_section` shared across document families;
- open, namespaced `document_categories` for family-specific structure;
- open, namespaced `domain_categories` for KnowledgeDomain structure;
- explicit normative, informative, or unspecified `annex_status`.

A deterministic `StructuralProfileClassifier` currently derives profiles from
references and headings. The model and classifier are implemented and tested,
but `StructuralProfile` is not yet persisted as a field of the canonical
`Clause` aggregate. Until that integration is completed, it must be treated as
an available classification contract rather than canonical stored clause data.

`SemanticClassification.document_structure` and `StructuralProfile` overlap in
purpose but serve different stages of the current transition. The former is the
persisted semantic representation; the latter provides the more general target
model for document-family and KnowledgeDomain structural taxonomies. Their
long-term consolidation requires an explicit follow-up architecture decision.

## Annotations, relations, and lineage

Annotations remain separate from source clauses. Their visibility controls
whether they may be exported publicly. Semantic relations are stored within
`SemanticClassification`, while annotation records retain reviewer and
qualification information without mutating protected source content.

Artifact lineage records how the aggregate was derived. `NormalizedDocument`,
reference candidates, alignments, transformation ledgers, and similar objects
are pipeline contracts and evidence; they are not substitutes for the canonical
`EngineeringDocument` aggregate.
