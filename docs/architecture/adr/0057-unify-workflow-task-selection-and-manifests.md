# ADR 0057: Unify workflow task selection and manifest inputs

## Status

Accepted, partially superseded by ADR 0058.

The `plan`/`run` operation model and `documents|qualification` task selection remain active.
ADR 0058 supersedes this record's separate `--manifest` and `--qualification-manifest`
interface with the typed, repeatable `--manifests` workflow envelope.

## Context

The workflow CLI had accumulated three top-level workflow operations: `plan`, `run`, and
`qualification-plan`. The qualification-specific planning command duplicated the operation
concept instead of expressing which end-to-end task should be planned. At the same time,
the standards definition was exposed as a `--catalog` input under `catalogs/`, while the
qualification matrix used a separate manifest vocabulary. This made orchestration harder
to discover and gave two executable YAML configuration classes inconsistent names.

Qualification execution also needs to preserve the existing document review gates. Corpus
construction and matrix evaluation must not run while AtlasData or alignment review is
still pending.

## Decision

The workflow CLI exposes only two operations:

- `workflow plan`
- `workflow run`

Both select the end-to-end workflow with `--task documents|qualification`. `documents`
remains the default for compatibility with the established document pipeline.

The standards configuration is supplied as `--manifest` and its canonical repository path
is `manifests/standards.yaml`. The qualification task accepts its matrix configuration via
the unambiguous `--qualification-manifest` option. The canonical checked-in matrix manifest
is versioned by both matrix and corpus identity:

`manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml`.

The qualification task reuses the existing document workflow through Markdown, excludes
Doorstop export and publication, then appends corpus build and qualification matrix stages.
`--regenerate-docling` includes fresh Docling extraction and invalidates downstream derived
artifacts. `workflow run --task qualification` does not execute corpus or matrix stages while
any document review gate remains open.

Workflow run reports use manifest terminology and record the selected task plus the optional
qualification manifest as provenance inputs.

## Consequences

The CLI has one operation axis (`plan` versus `run`) and one task axis (`documents` versus
`qualification`) instead of task-specific commands. Scripts using `workflow
qualification-plan` or workflow `--catalog` must migrate. Internal application model names
such as `StandardCatalog` remain unchanged because this decision concerns executable
configuration and CLI vocabulary rather than the domain model.

Keeping both checked-in executable YAML configurations under `manifests/` makes their role
and version identity visible at the repository boundary and simplifies reproducible workflow
commands.
