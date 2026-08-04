# ADR 0054: Model engineering knowledge as an orthogonal ontology

## Status

Accepted

## Context

The multidimensional qualification matrix still produced 25 disputed clauses out of 500.
Review showed a recurring taxonomy gap: clauses describing techniques, measures, and
methods were forced into statement-function labels such as `description`, `objective`,
or `recommendation`. IEC 61508-7, *Overview of techniques and measures*, demonstrates
that this is a first-class knowledge dimension rather than an exceptional wording style.

## Decision

Add `KnowledgeKind` as an independent clause-level ontology dimension. Version 2.0.0 of
the statement-function task exposes `knowledge_kinds` and `primary_knowledge_kind` with
the initial vocabulary:

- `technique`
- `measure`
- `method`
- `process`
- `artifact`
- `role`
- `evidence`
- `concept`

Knowledge kind is orthogonal to statement function, process function, applicability,
responsibility, structure, and normative status. An informative clause may therefore be
classified as `description` plus `technique`; a normative clause may be `requirement`
plus `measure`.

Qualification proposals, adaptive interviews, model consensus, Golden Corpus proposals,
and human review preserve this dimension explicitly. Existing version-2 proposal runs
must be regenerated because their response schema does not contain the new required
properties.

## Consequences

The ontology supports queries such as "which verification methods are described?" and
avoids using `description` as a surrogate for engineering content. The initial vocabulary
is intentionally broad and versioned; domain-specific refinements continue to use
`domain_functions` rather than expanding the central enum without cross-domain evidence.

## Amends

- ADR 0051: Multidimensional semantic classification
- ADR 0052: Build Golden Corpus proposals from model consensus
