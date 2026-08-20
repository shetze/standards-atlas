# ADR 0074: Materialize deterministic semantic routing as workflow artifacts

- Status: Accepted
- Date: 2026-08-20

## Context

ADRs 0072 and 0073 established the deterministic routing domain and independently versioned
routing-contract resources. The remaining runtime boundary is to apply one selected contract to
taxonomy output without storing routing policy inside either the taxonomy-owned
`StructuralProfile` or the ontology-owned `SemanticClassification`.

Routing decisions are execution and provenance data. They may differ for the same clause when a
different routing contract is selected, so persisting one routing result directly on `Clause`
would make the canonical document depend on one integration policy.

## Decision

Introduce `SemanticRoutingService` between structural taxonomy and semantic ontology execution.
For every clause it projects the materialized `StructuralProfile` and `StructuralContext` into a
`TaxonomySignalProfile`, evaluates the selected versioned `RoutingContract` with
`DeterministicRoutingEngine`, and materializes the resulting `SemanticRoutingPlan`.

Persist routing outside `EngineeringDocument` as a versioned private artifact:

```text
.atlas/data/routing/<document>/<contract-id>/<contract-version>/routing.json
```

The artifact contains the exact taxonomy signal profile used for each clause together with the
matched rules, dispositions, reasons, and context hints. This preserves auditability while
allowing multiple contracts to be evaluated against the same canonical document.

Add the low-level command:

```bash
uv run standards-atlas document route-semantics DOCUMENT \
  --manifest manifests/functional-safety-semantic-routing-v1.yaml
```

When a `routing_contract` manifest is included in the unified workflow manifest set, insert the
`routing` stage immediately after `taxonomy`. The production document workflow then proceeds to
`ontology`; qualification workflows continue to omit the production ontology stage but retain the
routing artifact before corpus construction.

Slice 3 does not yet make semantic-task execution conditional on dispositions. The current
contract still routes the monolithic `semantic-profile-classification@2.2.0` task as `required`.
Specialized task execution and consumption of `required`, `preferred`, `optional`, and `skip`
belong to the subsequent task-splitting slice.

## Consequences

Taxonomy, routing, and ontology now have separate persisted/runtime ownership boundaries. Routing
is reproducible from a concrete contract version and concrete taxonomy evidence without modifying
the canonical document.

Workflow overwrite policy treats routing artifacts as derived data. Changing the selected
contract version naturally changes the artifact path, while `--overwrite` regenerates routing
along with downstream derived stages.

Qualification can now collect deterministic routing evidence before any new task-specific LLM
execution is introduced. This allows routing coverage and expected call reduction to be measured
independently from model quality in the next slice.
