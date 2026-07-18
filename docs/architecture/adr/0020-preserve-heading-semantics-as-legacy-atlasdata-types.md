# ADR 0020: Preserve heading semantics as legacy AtlasData types

## Status

Accepted

## Context

The canonical domain model represents the meaning of a clause through one or
more `SemanticRole` values. The compact AtlasData `structure` syntax predates
that model and encodes a small set of clause types through prefixes such as
`s`, `t`, `o`, and `r`.

New AtlasData skeletons can be generated from Docling section headings. These
headings occasionally state an established legacy category explicitly, for
example `Scope`, `Terms and definitions`, `Objective`, or `Requirements`.
Existing AtlasData consumers expect those categories to remain visible through
the legacy type prefixes.

At the same time, treating the legacy type system as the canonical semantic
model would prevent clauses from carrying multiple roles and would make future
classification dependent on the structure notation.

## Decision

Docling onboarding preserves the complete public heading as the AtlasData TOC
title. It also derives a legacy AtlasData type marker when the heading contains
one of the categories supported by the existing format:

- `Scope` -> `s`
- `Terms and definitions` -> `t`
- `Objective` or `Objectives` -> `o`
- `Requirement` or `Requirements` -> `r`

Matching is case-insensitive and based on complete words.

An explicitly identified `Terms and definitions` clause establishes a
terminology subtree. Its descendants are emitted as terms even when a term name
contains words such as `scope`, `objective`, or `requirement`. This inherited
term classification takes precedence over keyword classification.

No additional semantic categories are added to the AtlasData structure syntax.
The imported `EngineeringDocument` continues to use `Clause.semantic_roles` as
the canonical representation. Existing AtlasData prefixes are compatibility
metadata from which initial semantic roles can be derived.

## Consequences

- Generated AtlasData remains compatible with existing tools and datasets.
- Clause headings are retained without rewriting or removing semantic words.
- ISO terminology sections are no longer assumed to be Clause 3; they are
  detected from their heading.
- Terms named, for example, `audit scope` remain terms rather than being
  misclassified as scope clauses.
- New roles such as bibliography, conformance, inputs, or outputs do not require
  new structure prefixes and can be represented solely in the domain model.
- Heading-based classification remains conservative and can later be replaced
  or supplemented by a dedicated semantic classification service.
