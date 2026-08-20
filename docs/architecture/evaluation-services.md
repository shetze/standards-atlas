# Evaluation architecture

![Evaluation architecture](diagrams/svg/evaluation-architecture.svg)

The diagram separates generic evaluation from semantic qualification and their principal artifacts. It groups the many runners, repositories, review helpers, consensus services, matrix models, and report types to keep the dependency direction readable.

Standards Atlas separates provider-neutral evaluation infrastructure from standards-specific semantic qualification.

## Generic evaluation

`application.evaluation` owns versioned prompts, schemas, datasets, runners, per-case observations, aggregate metrics, regression comparison, and reports. It depends on the `LlmGateway` port but has no knowledge of clauses, structural taxonomies, standards publication policy, or HITL annotation precedence.

## Semantic qualification

`application.semantic_qualification` adds:

- transport-neutral clause discovery through `ClauseProvider`;
- representative stratified corpus construction;
- structural-profile and semantic-classification tasks;
- reference extraction and resolution;
- baseline and model proposal runs;
- local Markdown review and reviewed-data publication;
- qualification matrices and repeated observations;
- model consensus and golden-corpus proposals;
- adaptive interview planning for difficult review cases.

It may depend on generic evaluation; the reverse dependency is forbidden.

## Qualification cascade

![Qualification cascade](diagrams/svg/qualification-cascade.svg)

Qualification uses a dimension-aware, monotonic cascade rather than rerunning every clause
through every model. The efficient-local stage produces repeated observations and an initial
consensus. Dimensions that reach an accepted decision are captured with provenance and remain
resolved; later disagreement in unrelated dimensions does not reopen them. Knowledge kind
currently has no cascade escalation rule and is therefore final after the initial stage.

Only clauses and dimensions with explicit escalation reasons continue to the intermediate
stage. Statement function can use a stage-local resolver, while applicability and
responsibility continue to use cumulative evidence. Remaining unresolved dimensions proceed
to the final candidate set and final resolver. Optional HITL review can then resolve disputed
or suspicious cases. All observations, resolution provenance, review evidence, metrics,
manifests, and corpus identity are preserved in the immutable `qualification-run-NNN.zip`
evidence bundle.

## Artifact separation

Corpora, proposal runs, reviewed annotations, consensus reports, and qualification reports are separate artifacts. Published reviewed data has higher authority than local review files; local review has higher authority than generated proposals only where the repository policy explicitly states this.

## Matrix execution

A matrix candidate is a reproducible combination of model, prompt, context mode, reasoning configuration, repetition, and runtime settings. Execution persists observations incrementally so `--resume` can continue incomplete work. `--overwrite` replaces selected outputs; `--recompute` intentionally reruns completed observations. Metrics distinguish availability, parse success, prediction success, agreement, calibration, and task quality.

## Normalization quality qualification

`application.normalization_quality` is an optional, read-only evaluation capability for
linguistic integrity checks over already normalized clause text. It reuses existing evaluation
corpora as clause samples but ignores their semantic gold labels. The LLM classifies only
probable extraction or normalization artifacts and never rewrites EngineeringDocuments.

Slice 1 intentionally separates this observational model qualification from the deterministic
normalization pipeline and from any future HITL correction workflow. Reports persist complete
per-model observations, suspicious findings, agreement/disagreement counts, cache information,
and a Markdown view optimized for manual inspection.

## Deterministic pipeline qualification

`application.qualification` is a separate application capability for reproducible
extraction and normalization checks against checked-in golden corpora. Its
`GoldenCorpusQualifier` and `QualificationRunReporter` verify deterministic pipeline
contracts and persist auditable reports. This package does not own LLM, prompt,
consensus, or semantic annotation qualification.

## Compatibility

`application.services.evaluation` currently re-exports canonical generic-evaluation and
semantic-qualification types for older imports. It is a compatibility facade only, not
an ownership boundary. New code must import `application.evaluation` or
`application.semantic_qualification` directly. Removal of the facade requires an
explicit compatibility decision because external users may still import it.
