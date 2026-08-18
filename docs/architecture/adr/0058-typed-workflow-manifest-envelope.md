# ADR 0058: Use typed workflow manifests behind one CLI option

## Status

Accepted.

## Context

Workflow tasks increasingly combine independently versioned configuration documents. Adding a
new CLI option for every manifest type couples the command surface to every future workflow.

## Decision

`workflow plan` and `workflow run` accept workflow configuration only through the repeatable
`--manifests` option. Each occurrence may contain one path or a comma-separated list of paths.
All workflow manifests start with the common envelope:

```yaml
manifest_type: <stable type>
schema_version: <schema version>
```

The currently supported types are `standards` and `qualification_matrix`. Manifest order and
file names have no semantic meaning. A task declares which manifest types it requires and the
loader rejects missing, duplicate, or unsupported types before planning starts.

The standards manifest uses `schema_version` instead of the previous generic `version` field.
Domain/application versions such as matrix, corpus, task, or dataset versions remain separate
payload fields and are not encoded into `manifest_type`.

## Consequences

New workflow manifest types can be added without adding dedicated CLI options. Workflow run
reports record the complete manifest list as provenance. Existing invocations using workflow
`--manifest` or `--qualification-manifest` must migrate to `--manifests`.
