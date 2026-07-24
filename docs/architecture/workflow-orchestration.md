# Workflow orchestration

![Workflow orchestration](diagrams/svg/workflow-orchestration.svg)

The end-to-end workflow service converts catalog intent into an ordered plan of executable CLI steps. Planning is side-effect free and exposes manual gates before execution.

A workflow may select explicit families, a profile, or all families. Exactly one selection mode is required. Execution stops when an unresolved alignment review or AtlasData baseline review is needed. `--continue-after-review` allows progress only when the expected reviewed artefact exists.

The workflow orchestrator does not implement extraction, normalization, or export logic itself. It composes application services and preserves their replacement rules, diagnostics, and failure semantics.
