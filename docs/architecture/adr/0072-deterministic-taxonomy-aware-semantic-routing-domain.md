# ADR 0072: Deterministic taxonomy-aware semantic routing domain

- Status: Accepted
- Date: 2026-08-20

## Context

Structural taxonomy already provides deterministic evidence before semantic LLM analysis,
while ontology definitions independently describe semantic meaning. Directly embedding
knowledge of one side in the other would couple taxonomy evolution to ontology evolution.
The semantic-analysis pipeline therefore needs an explicit integration boundary that can
later be populated by a versioned routing contract.

## Decision

Introduce a separate deterministic routing domain under `application.routing`.

The routing domain exposes:

- `TaxonomySignalProfile` as a normalized view of explicit structural evidence;
- a closed, declarative matcher vocabulary for scalar signals, namespaced taxonomy
  categories, heading text, and `all`/`any`/`not` composition;
- `RoutingRule` and the in-memory `RoutingContract` model;
- `RoutingDisposition` with the precedence `required > preferred > optional > skip`;
- `RoutingDecision` and `SemanticRoutingPlan` as auditable routing output; and
- `DeterministicRoutingEngine` to evaluate matching rules without LLM inference.

Taxonomy evidence may select or prioritize a semantic task, but routing must never translate
one taxonomy category into an ontology value. For example, a verification category may make
role-relation extraction preferred; it must not imply a `verifies` relation.

Contract persistence, resource loading, manifest integration, and workflow execution are not
part of this slice. They will build on the in-memory domain contract in later slices.

## Consequences

Taxonomy and ontology remain independently replaceable. Routing decisions are deterministic,
order-independent, explainable through matched rule identifiers, and testable without an LLM.
The closed matcher vocabulary avoids arbitrary expression execution and gives future routing
contract schemas a stable validation target.

The routing layer intentionally introduces a third architectural concern between structural
evidence production and semantic task execution. This additional boundary is preferable to
implicit coupling because it makes the integration policy explicit and versionable.
