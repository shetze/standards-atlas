# ADR 0012: Semantic Qualification and Evidence Model

## Status
Accepted

## Context
LLM-based semantic inference must be evaluated reproducibly across models, prompts, dimensions, and hard cases without turning transient model output into canonical truth.

## Decision
Semantic evaluation is an evidence-producing subsystem with explicit corpora, proposals, review, qualification, and archival.

- Representative versioned corpora are built from canonical physical documents.
- Model proposals are persisted resumably and remain separate from reviewed annotations.
- Consensus may propose golden annotations, but publication requires explicit review where configured.
- Clause references are extracted/resolved before semantic evaluation when they materially affect context.
- Qualification runs measure dimensions independently and may use deterministic routing/escalation policies.
- Role presence and role-relation tuples are qualified separately.
- Ontology-guided concept/relation extraction is qualified as inferred semantic evidence.
- Completed run/suite artifacts are archived immutably with sequential identity, configuration/manifests, hashes, routing/context artifacts, and relevant metrics.
- Human-facing review material belongs in local review/report locations; machine evidence belongs in workspace/evaluation storage.

## Consequences
Model changes can be compared without modifying canonical documents. Qualification results are reproducible and auditable.
