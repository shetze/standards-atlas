# ADR 0041: Keep semantic evaluation data local and reports content-safe

## Status

Accepted

## Context

Semantic evaluation requires representative clauses from licensed engineering standards. Prompt
benchmarking and model comparison may additionally produce model responses derived from those
clauses. These artefacts are useful for engineering work but may contain copyrighted or otherwise
protected content.

At the same time, benchmark results must be reproducible, comparable, and suitable for regression
qualification. A useful report therefore needs stable identifiers, versions, hashes, configuration,
and metrics without automatically copying protected text into shareable artefacts.

## Decision

Standards Atlas separates local evaluation corpora from content-safe benchmark evidence.

Corpus construction produces versioned, annotation-ready datasets below the local workspace. Each
corpus records stable clause identifiers, document references, source hashes, sampling strategy,
seed, filters, and annotation state. A hashes-only mode is available when even local corpus exports
must omit clause text.

Prompt and model matrices are declared in versioned manifests. The effective manifest receives a
stable SHA-256 fingerprint that is propagated into run reports.

Matrix summaries omit clause text, gold answers, and model responses by default. They contain only
metrics, validation results, timings, hashes, model and prompt versions, errors, and the manifest
fingerprint. Case-level content may be included only through an explicit local configuration.

## Consequences

### Positive

- Licensed standard text is not copied into ordinary benchmark reports.
- Prompt and model comparisons remain reproducible and auditable.
- Reports can be retained as qualification evidence with reduced disclosure risk.
- Corpus annotation and benchmark execution remain separate lifecycle steps.
- Hashes allow source changes to be detected without exposing source content.

### Negative

- Content-safe reports are insufficient for detailed error analysis by themselves.
- Reviewers need access to the protected local corpus for case-level diagnosis.
- Explicit policies are required when reports leave the local environment.

## Alternatives considered

### Store all prompts, clauses, and responses in every report

Rejected because it would unnecessarily replicate protected content and make reports difficult to
share or archive safely.

### Store only aggregate metrics

Rejected because aggregate numbers alone do not provide enough provenance to reproduce or compare a
benchmark run.

### Use a remote evaluation service as the canonical store

Rejected because the project must support fully local evaluation of licensed standards and local
models.
