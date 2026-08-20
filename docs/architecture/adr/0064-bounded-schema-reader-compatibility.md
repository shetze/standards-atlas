# ADR 0064: Bound persisted-schema compatibility at the reader boundary

## Status

Accepted.

## Context

ADR 0063 established a destructive clean baseline for persisted JSON/YAML contracts.
Standards Atlas needs enough backward compatibility to read recently produced durable
artifacts, but it must not accumulate an unbounded chain of legacy readers or generic
migration infrastructure.

Generated artifacts do not require in-place migration. Cache and workflow scratch data
are disposable and are not compatibility contracts.

## Decision

Each compatibility-relevant schema family has one `SchemaPolicy` with one current
schema version and an ordered set of readable versions.

Regular support is bounded to at most three versions: the current schema and at most
two predecessors. A Standards Atlas major-version transition may temporarily declare a
four-version window. That exception must be explicit on the policy and is not the
normal state.

Readers validate through the schema policy. Reading a supported non-current schema
emits a visible `SchemaDeprecationWarning` derived from `UserWarning`, rather than
Python's normally hidden `DeprecationWarning`. The oldest member of a full three-version
window additionally warns that it will leave support on the next schema revision.
Unsupported versions fail explicitly.

Writers emit only the current schema. Compatibility is therefore a bounded
reader concern, not a bidirectional serializer or data-migration subsystem.

After ADR 0063, all concrete policies initially contain only their current baseline.
Historical schemas are not reintroduced merely to fill the compatibility window.
Future schema revisions add predecessor readers deliberately when they are needed.

Semantic task, ontology, structural taxonomy, Engineering Document, and
workflow-manifest loaders are routed through the shared reader policy where applicable.

## Consequences

- Reader compatibility cannot grow without bound.
- Deprecation is visible to CLI/workflow users through normal warning handling.
- Old generated data can remain usable for a bounded period without being rewritten.
- No generic migration chain or `standards-atlas migrate` command is introduced.
- `.atlas/cache` and `.atlas/work` remain outside the compatibility guarantee.
- Removing an old schema means removing its reader path when it leaves the declared
  policy window.
