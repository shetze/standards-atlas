# ADR 0011: Workflow Orchestration and Stage Boundaries

## Status
Accepted

## Context
The project supports document production, corpus construction, and qualification. Earlier workflows mixed deterministic production with model-driven semantic classification and accumulated overlapping CLI/manifests.

## Decision
A unified manifest-driven workflow planner/executor coordinates typed tasks and artifacts, with strict stage ownership.

The principal workflows are:

- **documents**: extraction/onboarding, normalization, enrichment, structural taxonomy, composition/publication. This workflow is deterministic with respect to semantic interpretation and must not require LLM services.
- **corpus**: builds evaluation corpora from canonical physical documents and explicitly selected semantic/profile resources.
- **qualification**: may run semantic classification/extraction and qualification over canonical documents using persisted structural context.

Typed manifest envelopes declare resources and task configuration. `--overwrite` rebuilds owned artifacts; resumable execution reuses valid persisted artifacts according to workflow contracts. Workflow stages must not implicitly perform work owned by another stage.

## Consequences
Production document generation remains deterministic and robust when LLM services are unavailable. Semantic inference is explicit, measurable, and qualification-focused.
