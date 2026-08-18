# ADR 0059: Archive qualification runs as immutable sequential evidence

## Status

Accepted

## Context

Qualification analysis archives were previously stored beneath the active matrix working
output and encoded matrix ID, archive schema version, and Standards Atlas version in both
path and filename. This produced long paths such as
`local/evaluation/qualification/<matrix-id>/<matrix-id>-qualification-analysis-...zip`
and conflated the qualification-matrix definition with one concrete execution of it.

The archive itself already contains the detailed reports and configuration needed to
identify a run. Encoding the same metadata in the filename is redundant and makes the
archive naming brittle as further versions are introduced.

## Decision

1. Treat each completed qualification execution as an immutable **qualification run**.
2. Store archived evidence directly below `local/evaluation/` using monotonically
   increasing names `qualification-run-NNN.zip`.
3. Never reuse or overwrite a run sequence number, including during `--overwrite` runs.
4. Embed `qualification-run-metadata.json` in every archive. It records the archive ID and
   sequence, Standards Atlas version, qualification-manifest schema, matrix and corpus IDs,
   task and dataset versions, prompt versions, model references, manifest hash, and stable
   result metrics.
5. Keep `archive-manifest.json` as the file-integrity manifest for the ZIP and include the
   metadata file in its SHA-256 inventory.
6. Maintain `local/evaluation/qualification-run-index.json` as a derived navigation index
   with the latest sequence and compact metadata for all known archived runs.
7. Keep active/replaceable qualification working outputs below
   `local/evaluation/qualification/<matrix-id>/`; immutable archives are separate evidence.

## Consequences

- Filenames remain short and stable while the archive remains fully self-describing.
- A run sequence identifies a concrete execution, not a semantic version of the matrix.
- Matrix, corpus, task, dataset, prompt, model, and tool versions remain explicit metadata
  rather than being inferred from filenames.
- `--overwrite` can replace working outputs without destroying historical evaluation
  evidence.
- The index enables future commands such as qualification history or run comparison without
  opening every ZIP.
