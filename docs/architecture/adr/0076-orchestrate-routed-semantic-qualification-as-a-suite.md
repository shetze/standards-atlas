# ADR 0076: Orchestrate routed semantic qualification as a suite

## Status

Accepted.

## Context

ADR 0075 split the monolithic semantic-profile qualification task into five independently
qualified tasks. Running one `qualification_matrix` manifest directly is intentionally a
low-level operation, but it does not provide the end-to-end behavior of the former
`workflow run --task qualification` command. In particular, callers would otherwise need to
materialize structural taxonomy and routing artifacts manually and then invoke five matrices
one by one.

The first split-task manifests also used `full_matrix` execution. That bypassed the established
local-first cascade and made expensive/reference candidates appear before the efficient local
stage. Applicability and role-relation manifests additionally accepted the `optional` routing
baseline, which effectively routed nearly the whole corpus and defeated the purpose of the
new deterministic gate.

## Decision

Introduce a third workflow task, `routed-qualification`, and a versioned
`qualification_suite` manifest.

The suite is an orchestration contract only. It references one routing-contract manifest and
an ordered set of qualification-matrix manifests. The routed qualification planner validates
that all five split semantic tasks are present exactly once and that every matrix consumes the
same routing-contract identity/version selected by the suite.

The workflow performs document preprocessing through structural taxonomy and deterministic
routing, omits production ontology and Doorstop publication, then executes one corpus-build and
one qualification-matrix step for each split task in suite order.

The v4 split-task matrices use the established three-stage cascade: efficient local models,
intermediate escalation, and final escalation. Applicability and role-relation extraction use
`preferred` as their minimum routing disposition so taxonomy-derived routing actually limits
LLM work. The three core classification tasks remain `required` for the complete corpus.

The legacy `qualification` workflow remains available for reproducing one matrix manifest.
Direct `evaluation qualification-matrix` remains a low-level single-matrix command.

## Consequences

A complete routed qualification can again be invoked with one workflow command while keeping
individual semantic tasks independently versioned and reproducible. The suite provides the
missing orchestration layer without merging task manifests back into a monolith.

Routing is now operationally meaningful for specialized extraction tasks: clauses left at the
`optional` baseline are not sent to Applicability or Role Relation qualification. Contract
rules can promote clauses to `preferred` without embedding taxonomy knowledge in the semantic
tasks themselves.

Changing suite membership, ordering, routing contract, or matrix versions is explicit and
versioned. Reproducing the old monolithic qualification remains possible through its existing
manifest and workflow task.
