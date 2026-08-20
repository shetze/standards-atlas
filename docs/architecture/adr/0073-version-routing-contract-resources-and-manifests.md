# ADR 0073: Version routing contracts as resources selected by manifests

- Status: Accepted
- Date: 2026-08-20

## Context

ADR 0072 introduced an in-memory deterministic routing domain so structural taxonomy evidence
can select semantic analysis tasks without translating taxonomy categories into ontology
values. Persisting that integration policy inside taxonomy definitions, semantic task
resources, or workflow code would recreate the coupling that the routing boundary is meant to
avoid.

Routing policy must therefore be independently versioned, reproducible, and selectable by the
workflow envelope before execution is introduced. Runtime execution is specified by ADR 0074.

## Decision

Persist routing contracts below `resources/routing-contracts/<id>/<version>/routing.yaml` and
load them through the `RoutingContractRepository` port. The packaged-resource adapter validates
the routing schema and requires the resource `id` and `version` to match its resource path.

A persisted contract declares:

- the concrete structural taxonomy identities and versions whose signals it expects;
- the semantic task identities and versions that its rules may address; and
- deterministic rules using the closed matcher vocabulary introduced by ADR 0072.

Rules may address only tasks declared by the same contract. Taxonomy requirements and task
references are identities, not semantic mappings: no routing resource may translate a taxonomy
category into an ontology value.

Add the workflow manifest type `routing_contract`. A routing manifest contains only the common
manifest envelope plus a versioned contract reference. The manifest selects a resource; it does
not duplicate routing rules.

The first packaged contract is
`functional-safety-semantic-profile@1.0.0`. It binds the current
`domain.functional-safety@1.0.0` taxonomy to the existing
`semantic-profile-classification@2.2.0` task and routes that monolithic task as required. This
intentionally preserves current semantic behaviour. ADR 0074 subsequently adds deterministic
workflow execution and routing-artifact persistence; conditional specialized task execution remains
a later slice.

## Consequences

Routing policy can evolve independently from both taxonomy implementations and semantic task
resources. A qualification or production run can record the exact taxonomy, semantic task, and
routing-contract versions that governed task selection.

The workflow manifest registry can discover one routing-contract manifest alongside the standards
and qualification-matrix manifests. ADR 0074 adds the execution boundary that consumes this
selection after taxonomy while keeping semantic-task execution unchanged.

Routing contracts now have their own schema family and bounded compatibility policy. This makes
future contract migrations explicit rather than relying on permissive YAML parsing.
