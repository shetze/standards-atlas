# ADR 0014: Schema and Artifact Versioning Policy

## Status
Accepted

## Context
Refactoring changes persisted artifact schemas frequently. Unbounded compatibility code obscures the current model and increases test/support cost.

## Decision
Interfaces are versioned when they cross a persistence, process, packaged-resource, plugin, or otherwise independently evolving lifecycle boundary. Ordinary internal Python interfaces are not versioned merely because they are architectural boundaries.

Schema versions answer whether an artifact can be deserialized. Semantic/resource versions identify the definition, profile, ontology, task, or configuration used to produce or interpret it. These version axes are independent and must not be coupled.

### Refactoring transition
During the current architectural refactoring there is no general backward-compatibility obligation for intermediate versions. Obsolete transition schemas and migration code may be removed. Writers emit only the current schema and readers may intentionally accept only that schema. Unsupported versions fail clearly.

The compatibility infrastructure is retained because this exception is temporary; it must not be used as a reason to preserve obsolete refactoring contracts.

### Stable compatibility policy
Before the refactoring is declared complete, persisted and independently consumed interfaces shall adopt the stable policy:

- writers emit only the current version `N`;
- readers accept `N` and the two immediately preceding versions `N-1` and `N-2`;
- reading `N-1` or `N-2` emits a deprecation warning;
- versions older than `N-2` are rejected clearly; and
- resource/profile/task versions continue to evolve independently of serialization schema versions.

## Consequences
The refactoring can remove obsolete intermediate structures aggressively without discarding the mechanism required for a bounded post-refactoring compatibility contract. The stable support window is explicit: current plus two previous versions, with current-only writes and deprecation warnings for older readable versions.
