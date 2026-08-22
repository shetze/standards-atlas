# ADR 0073: Qualify role presence and relation tuples separately

## Status

Accepted.

## Context

Role qualification previously reduced a clause to `role_relation_present` plus one
`primary_role_relation_type`. This made a unanimous negative vote look strong even
when a clause contained obvious role semantics, and it discarded actor and target
agreement from structured `RoleRelation` proposals.

Slice 2 separated production role-semantics presence detection from grounded
relation extraction. Qualification must preserve that distinction without
introducing another routing or matrix orchestration layer.

## Decision

The multidimensional qualification matrix remains the single orchestration path,
but role evaluation is split into two independent signals:

1. `role_semantics_present` is qualified as a presence decision. It does not require
   a complete actor-relation-target tuple.
2. `role_relations` are qualified as a set of normalized complete tuples rather
   than as one primary relation label.

A deterministic role-candidate marker records lexical signals such as role,
responsibility, verification, validation, approval, independence, supplier, or
manufacturer terms. The marker is diagnostic only: it never overrides an LLM vote.
A candidate-positive/consensus-negative clause is surfaced as a hard-case signal.

Tuple comparison exposes actor, relation, target, and evidence agreement separately,
and complete tuple precision/recall/F1 can be computed when reviewed or golden
relations are available.

The legacy scalar role-relation fields remain readable during the schema transition,
but are no longer required by the new semantic-profile task contract.

## Consequences

Qualification can now distinguish "role semantics exist but no explicit actor can
be extracted" from "no role semantics exist". Multiple relations per clause are
preserved. Sparse negative consensus can be inspected against deterministic
candidate evidence instead of being treated as inherently high-quality.

The focused golden role corpus remains a later slice; until it exists, tuple-set
consensus is model consensus rather than correctness against human-reviewed gold.
