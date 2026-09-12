# ADR 0012: Semantic Qualification and Evidence Model

## Status
Accepted

## Goal alignment
Qualification is the trust boundary that makes LLM-assisted knowledge engineering suitable for traceable technical content. The objective is not to maximize generated triples, but to establish evidence for which semantic functions, concepts, and relations may be accepted and projected into CBox/ABox knowledge.

The intended trust chain is:

```text
formal assertion -> accepted extraction/context -> qualification/provenance -> clause -> EngineeringDocument -> source evidence
```

## Context
LLM-based semantic inference must be evaluated reproducibly across models, prompts, dimensions, and hard cases without turning transient model output into canonical truth.

## Decision
Semantic evaluation is an evidence-producing subsystem with explicit corpora, proposals, review, qualification, and archival.

- Representative versioned corpora are built from canonical physical documents.
- Model proposals are persisted resumably and remain separate from reviewed annotations.
- Consensus may propose golden annotations, but publication requires explicit review where configured.
- Clause references are extracted/resolved before semantic evaluation when they materially affect context.
- Qualification runs measure dimensions independently and may use deterministic routing/escalation policies.
- Applicability Presence is decided in the shared central cascade. Detailed Applicability functions are extracted only from the final positive subset in a separate sparse post-consensus stage and never revise the Presence decision.
- Role presence and role-relation tuples are qualified separately.
- Ontology-guided concept/relation extraction is qualified as inferred semantic evidence.
- Completed run/suite artifacts are archived immutably with sequential identity, configuration/manifests, hashes, routing/context artifacts, and relevant metrics. Before archival, enabled sparse stages must be complete and still match the current source Selection, coverage, consensus, task, prompt, model, and configuration. Their exact resources and clause-level evidence are archived with the validated summary.
- Human-facing review material belongs in local review/report locations; machine evidence belongs in workspace/evaluation storage.

### Baseline accounting and offline replay

Every selected clause remains in the cascade accounting, including missing initial or later
stage observations. A missing record cannot certify a dimension or an early exit. Unresolved
resolver reasons survive stage transitions until the existing acceptance rule is met.

Offline replay is an audit operation over immutable inputs: historical inspection, routing
against archived consensus, or consensus recomputation from verified local proposals. Missing
observations are explicit inference requirements, not fabricated negative votes. A replay is
not a fresh qualification and does not publish canonical or public enrichment changes.

Performance evidence distinguishes actual gateway calls, measured provider durations, cached
historical measurements and wall time. Per-request latency uses a measured-request denominator;
unknown retry/failure provider time remains unknown even when its wall time is measured.

## Consequences
Model changes can be compared without modifying canonical documents. Qualification results are reproducible and auditable, and accepted semantic evidence can be promoted deliberately into document context and formal knowledge projections without treating raw model output as truth.
