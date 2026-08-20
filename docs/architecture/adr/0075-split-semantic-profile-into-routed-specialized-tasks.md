# ADR 0075: Split semantic profile qualification into routed specialized tasks

- Status: Accepted
- Date: 2026-08-20

## Context

`semantic-profile-classification:2.2.0` asks one LLM response to classify statement functions,
knowledge kinds, process functions, applicability, and role relations. The dimensions are not the
same kind of inference: the first three are classifications, applicability is a focused semantic
analysis, and role relations are structured relation extraction. Requiring every model to emit the
combined schema increased prompt load and made structured role extraction depend on redundant
scalar relation fields.

Slices 1-3 introduced deterministic taxonomy-aware routing, versioned routing contracts, and
persisted per-clause routing plans. Those plans provide the boundary needed to execute independent
semantic tasks without coupling taxonomy categories to ontology values.

## Decision

Replace the active monolithic semantic-profile qualification contract with five independently
versioned tasks:

1. `statement-function-classification:3.0.0`
2. `knowledge-kind-classification:1.0.0`
3. `process-function-classification:1.0.0`
4. `applicability-extraction:1.0.0`
5. `role-relation-extraction:1.0.0`

Each task owns a focused canonical schema and four focused prompt variants. Qualification manifest
schema 1.6 can bind a matrix to a persisted routing contract and minimum routing disposition.
Routing happens before proposal generation and never changes ontology values.

Role-relation extraction uses `role_relations` as its LLM source of truth. Scalar
`role_relation_types` and `primary_role_relation_type` are derived deterministically after the raw
response satisfies the task schema. Grounded relation qualification additionally compares normalized
`role + relation + target + condition` tuples; evidence wording and confidence are provenance, not
identity.

The existing `semantic-profile-classification:2.2.0` resource remains readable for prior runs and
archives. The new `functional-safety-semantic-profile:1.1.0` routing contract addresses only the
specialized task identities.

## Consequences

- Models can be qualified independently for each semantic capability.
- Routing policy can reduce extraction calls without changing task semantics.
- Qualification metrics are projected onto the task's own dimension rather than implicitly scoring
  statement functions for every task.
- Role relation serialization no longer requires an LLM to duplicate the same information in scalar
  and structured forms.
- Split task matrices use full-matrix execution initially; cascade/consensus policy can be qualified
  independently per task later.
- Existing 2.2 qualification evidence remains reproducible and is not rewritten.
