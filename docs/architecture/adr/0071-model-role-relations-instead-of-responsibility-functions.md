# ADR 0071: Model role relations instead of responsibility functions

## Status

Accepted.

## Context

Qualification runs showed that the former `responsibility_functions` dimension was both
sparse and semantically lossy. `responsibility_assignment`, `responsibility_exclusion`,
and `role_condition` collapsed distinct statements about execution, verification,
validation, independence, prohibition, assignment, and role assumption into a narrow
responsibility vocabulary. A direct RACI classification would introduce a different
problem: standards often state who performs or verifies an activity without establishing
RACI `Accountable`, `Consulted`, or `Informed` semantics.

## Decision

Semantic profile 2.2.0 replaces the active responsibility dimension with
`role_relation_types`. The controlled vocabulary is `responsible_for`, `performs`,
`approves`, `verifies`, `validates`, `consulted_for`, `informed_about`, `independent_of`,
`excluded_from`, `assigned_to`, `assumes_role`, and `participates_in`.

Qualification prompts additionally return grounded `role_relations` containing the
verbatim role/actor, relation type, target, optional condition, evidence, and confidence.
A relation may be emitted only when both an identifiable actor/role and an explicit target
are supported by clause evidence. RACI is a downstream projection and must not be inferred
from weaker role relations.

The previous semantic-profile 2.0.0 and 2.1.0 resources remain available as older schema
slices. New qualification manifests use semantic-profile 2.2.0 and v4 prompts.

## Consequences

Qualification agreement is measured on the controlled relation type while retaining the
richer extracted relation for later knowledge-graph and matrix use. Independence and
separation constraints become first-class semantics. RACI views can safely map explicit
relations where justified, but `A`, `C`, and `I` remain absent unless the source provides
sufficient evidence.
