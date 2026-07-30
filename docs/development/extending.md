# Extending Standards Atlas

## Add an importer

Translate the external representation into an existing application contract. Preserve source evidence and keep vendor-specific objects inside the adapter.

## Add a normalization rule

Make the rule deterministic, order-aware, and lossless. Record its transformation effect and add focused plus corpus regression tests.

## Add a semantic classifier

Extend one explicit `SemanticClassification` dimension behind the application service boundary. Keep deterministic classification as the default, use the versioned dimension-specific evaluation tasks, and do not reintroduce a flat mixed-role vocabulary. Optional LLM support must be explicit and must not silently replace reviewed metadata.

## Add an exporter

Consume `EngineeringDocument`, define the target projection and visibility policy, and avoid writing target identifiers back into the domain.

## Add a workflow stage

Expose an application service first, define persisted input and output contracts, specify invalidation and replacement semantics, then add orchestration and CLI presentation.
