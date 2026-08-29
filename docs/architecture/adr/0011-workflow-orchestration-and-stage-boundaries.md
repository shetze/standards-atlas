# ADR 0011: Workflow Orchestration and Stage Boundaries

## Status
Accepted

## Goal alignment
The end-to-end target pipeline spans acquisition, canonical representation, context enrichment, qualified knowledge extraction, formal knowledge integration, retrieval/serving, interfaces, and applications. Workflow boundaries exist to make those transformations explicit and recoverable; they must not imply that qualification itself is the final product.

In particular, deterministic document construction and taxonomy must remain usable without LLM services, while model-assisted semantic context and ABox extraction occur only through explicit, qualified stages before accepted results are projected into the knowledge layer.

## Context
The project supports document production, corpus construction, and qualification. Earlier workflows mixed deterministic production with model-driven semantic classification and accumulated overlapping CLI/manifests.

## Decision
A unified manifest-driven workflow planner/executor coordinates typed tasks and artifacts, with strict stage ownership.

The principal workflows are:

- **documents**: extraction/onboarding, normalization, enrichment, structural taxonomy, composition/publication. This workflow is deterministic with respect to semantic interpretation and must not require LLM services.
- **corpus**: builds evaluation corpora from canonical physical documents and explicitly selected semantic/profile resources.
- **qualification**: runs model-assisted semantic classification/extraction and qualification over canonical documents using persisted structural context; accepted outputs provide evidence for later CBox/ABox projection.
- **knowledge projection/serving**: consumes canonical documents plus accepted/qualified semantic artifacts to build rebuildable CBox/ABox/OWL and retrieval projections. This capability may be exposed as its own workflow task as the implementation matures; it must not be hidden inside document construction.

Typed manifest envelopes declare resources and task configuration. `--overwrite` rebuilds owned artifacts; resumable execution reuses valid persisted artifacts according to workflow contracts. Workflow stages must not implicitly perform work owned by another stage.

## Consequences
Canonical document generation remains deterministic with respect to semantic interpretation and robust when LLM services are unavailable. Semantic inference is explicit, measurable, and qualification-gated. Knowledge projection and serving are downstream concerns and may evolve independently from both document construction and model qualification.
