# ADR 0014: Schema and Artifact Versioning Policy

## Status
Accepted

## Context
Refactoring changes persisted artifact schemas frequently. Unbounded compatibility code obscures the current model and increases test/support cost.

## Decision
Persisted engineering artifacts carry explicit schema versions and readers implement **bounded compatibility only when intentionally required**.

During the current refactoring there is no general backward-compatibility obligation. The current writer emits only the current schema. A reader may support a bounded set of older versions when there is a concrete migration/use case; unsupported versions fail clearly with the readable/current version range.

Schema versioning is distinct from semantic ontology/profile/task versions and from user-facing package versions.

## Consequences
The codebase can remove obsolete structures aggressively while still making supported compatibility explicit and testable.
