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

## Artifact separation

Corpora, proposal runs, reviewed annotations, consensus reports, and qualification reports are separate artifacts. Published reviewed data has higher authority than local review files; local review has higher authority than generated proposals only where the repository policy explicitly states this.

## Matrix execution

A matrix candidate is a reproducible combination of model, prompt, context mode, reasoning configuration, repetition, and runtime settings. Execution persists observations incrementally so `--resume` can continue incomplete work. `--overwrite` replaces selected outputs; `--recompute` intentionally reruns completed observations. Metrics distinguish availability, parse success, prediction success, agreement, calibration, and task quality.

## Qualification cascade and resolver

Multidimensional qualification is not a single majority vote. A matrix run persists model observations first, then resolves each semantic dimension independently. The productive cascade is conceptually:

```text
observations
    │
    ▼
dimension-specific consensus
    │
    ▼
resolution state + escalation reasons
    │
    ▼
next configured stage
    │
    ▼
stage/final resolver
    │
    ▼
final decision + provenance + HITL reasons
```

Thresholds and resolver behavior are manifest-driven and may differ by dimension. Statement-function resolution, applicability confidence, responsibility confidence, and structural applicability conflicts therefore do not have to share one acceptance rule. `cascade-provenance.json` records stage entry/exit reasons, configured versus effective policy, and before/after resolution counts so the final result can be explained without reconstructing execution from raw votes.

## Qualification evidence bundle

Every consensus-enabled qualification run is archived as an immutable sequential `local/evaluation/qualification-run-NNN.zip`. The ZIP is more than a convenience archive: it is the evidence envelope needed to interpret and reproduce the run. It contains the exact corpus and corpus manifest, qualification manifest, task and schema resources, referenced prompts, ontology definitions, relevant runtime configuration, observations and cascade reports, consensus/HITL artifacts, analysis metrics, metadata, and file hashes.

`qualification-run-metadata.json` is the canonical machine-readable identity of the bundle; `qualification-run-index.json` is a derived locator for comparing runs without opening each ZIP. Sequential run numbers are never reused by `--overwrite`.

## Challenger qualification

Challenger qualification is an isolated comparison workflow configured in the same qualification-matrix manifest. Challenger-only models are excluded from the productive matrix unless explicitly promoted into its production model set. The comparison can reuse difficult clause selections such as archived applicability conflicts and emits explicit selection provenance plus challenger comparison artifacts. Its metrics are observational: they support model-selection decisions but never mutate cascade roles automatically.

## Normalization quality qualification

`application.normalization_quality` is an optional, read-only evaluation capability for
linguistic integrity checks over already normalized clause text. It reuses existing evaluation
corpora as clause samples but ignores their semantic gold labels. The LLM classifies only
probable extraction or normalization artifacts and never rewrites EngineeringDocuments.

This capability intentionally separates observational model qualification from the deterministic
normalization pipeline and from any future HITL correction workflow. The LLM is a downstream
review instrument, not a normalization engine: findings may guide human review and future
deterministic rule changes, but the qualification command never edits canonical documents. Reports persist complete
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
