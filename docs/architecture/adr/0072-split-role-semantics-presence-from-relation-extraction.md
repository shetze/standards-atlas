# ADR 0072: Split role-semantics presence from role-relation extraction

## Status

Accepted.

## Context

Qualification of the role-relation model introduced by ADR 0071 showed a systematic
failure mode: a clause was considered role-relevant only when a complete actor-relation-
target tuple could be extracted. Passive statements such as "the analysis shall be
verified" therefore became indistinguishable from clauses with no role semantics at all.
The same task also mixed binary detection with structured relation extraction, making
model agreement difficult to interpret.

## Decision

Role processing is split into two focused semantic tasks:

1. `role-semantics-presence` decides whether explicit role, actor, responsibility,
   participation, assignment, approval, verification, validation, or organizational
   semantics are present. A complete actor-relation-target tuple is not required.
2. `role-relation-extraction` extracts zero or more explicit, evidence-grounded
   `RoleRelation` tuples. Each tuple requires an identifiable actor, controlled relation,
   identifiable target, and supporting evidence.

The production ontology service composes the tasks locally. Relation extraction runs only
when presence is true. This composition creates no routing contract, routing manifest, or
persisted routing artifact. Existing non-role semantic dimensions continue through the
composed `OntologyEngine` profile.

A positive presence result with an empty relation set is valid and intentionally represents
clauses whose role semantics are explicit but whose actor or target is not stated.

The existing multidimensional qualification matrix is not changed by this ADR. Qualification
of presence and relation tuples is a subsequent slice so that production task semantics and
qualification metrics remain separate concerns.

## Consequences

Role relevance no longer depends on successful tuple extraction. Passive role-bearing
statements can be represented without inventing actors. Relation extraction becomes a
focused structured-generation task and can preserve multiple relations per clause. The
production path incurs the presence request for role processing and invokes the more
expensive extraction request only for positive clauses.
