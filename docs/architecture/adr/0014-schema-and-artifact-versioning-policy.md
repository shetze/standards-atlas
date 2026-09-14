# ADR 0014: Schema and Artifact Versioning Policy

## Status
Accepted

## Goal alignment
Standards Atlas must allow taxonomies, semantic tasks, domain TBoxes, knowledge projections, retrieval backends, and interfaces to evolve without losing auditability. Independent schema and resource versioning supports that goal by preserving the exact semantic and processing context required to reproduce a derived assertion.

## Context
Refactoring changes persisted artifact schemas frequently. Unbounded compatibility code obscures the current model and increases test/support cost. At the same time, several independently evolving resources carry a domain/resource version in addition to their serialization schema. Treating these as one version axis couples readability to meaning and makes evolution unnecessarily expensive.

## Decision
An interface is versioned when it crosses a persistence, process, packaged-resource, plugin, public-contract, or otherwise independently evolving lifecycle boundary. Ordinary internal Python interfaces are not versioned merely because they are architectural boundaries. Runtime-only read models such as `PublicationDocument` are deliberately outside the versioned-interface inventory.

The executable inventory lives in `standards_atlas.application.schema.inventory`. Every interface that declares a serialization schema axis must map to exactly one central `SchemaPolicy` family.

### Independent version axes

Two version axes are distinguished:

- **schema version** answers whether a serialized JSON/YAML artifact can be read safely;
- **resource version** identifies the semantic definition, profile, ontology, taxonomy, task, prompt, or other independently selectable behavior represented by or referenced from that artifact.

Changing a resource version does not imply a schema change. Changing a schema version does not imply changed resource semantics. The two axes must not be coupled.

Semantic tasks, profiles, semantic ontologies, structural taxonomies, and formal ontologies therefore carry both axes. Semantic prompts are independently versioned resources but do not own an additional serialization schema; their output contract is owned by the task that consumes them.

### Refactoring transition

The project-wide compatibility phase is explicitly `REFACTORING`. During this phase there is no general backward-compatibility obligation for obsolete intermediate schemas. Writers emit only the current schema and concrete readers may intentionally accept only that current schema. Unsupported versions fail clearly.

The generic bounded-reader infrastructure remains active. The stable reader-window width is fixed at three, but removed refactoring schemas are not reintroduced merely to fill that window.

### Stable compatibility policy

Before the refactoring is declared complete, the project compatibility phase shall be changed to `STABLE`. From the first subsequent real schema evolution onward:

- writers emit only the current version `N`;
- readers accept `N` and up to the two immediately preceding real predecessor versions `N-1` and `N-2`;
- reading a supported non-current version emits a deprecation warning;
- versions outside that bounded reader window are rejected clearly; and
- resource/profile/task/prompt versions continue to evolve independently from serialization schema versions.

The policy does not require inventing migrations for schema versions that never formed a supported stable contract.

### Versioning ownership

The central schema registry owns lifecycle-crossing serialization contracts. Embedded implementation records may carry local version markers for auditability without becoming independent schema families. A local marker becomes a central schema contract when another process, persistence repository, packaged resource loader, plugin, or external consumer reads it independently.

## Consequences
The refactoring can remove obsolete intermediate structures aggressively without discarding the mechanism required for bounded post-refactoring compatibility. New lifecycle-crossing interfaces must be added to the executable inventory and, when schema-versioned, to `SCHEMA_POLICIES`. Schema and resource versions can evolve independently. Runtime-only projections do not create unnecessary compatibility obligations.

### Qualification baseline reporting contracts (2026-09-12)

The executable inventory includes cascade provenance (writer `1.6`, readers `1.5`/`1.6`),
qualification matrix reports (writer `1.1`, readers `1.0`/`1.1`), offline cascade replay
(`1.0`) and persisted per-case request timing (`1.0`). New reporting fields do not change
archive metadata, task, prompt, ontology, applicability policy or public enrichment schemas.
Historical reporting formats remain historical evidence; accepting their schema is not a
claim that an old ambiguous batch-time field is a measured per-request latency.

### Final qualification artifact contracts (Slice 7)

New schema-1.0 families are registered for `partial-qualification-campaign`,
`partial-qualification-repeat`, `partial-qualification-evaluation`,
`partial-semantic-reference`, `partial-qualified-activation`,
`qualification-request-event` and `partial-qualification-execution`. Unsupported versions
are rejected at their reader boundaries. Existing partial, public AtlasData, EngineeringDocument
and standard Qualification archive schema families are unchanged.

A frozen campaign hashes exact source/reference files and effective task/prompt/frame/rule
configuration. Each independent repetition has its own bound execution identity and sealed
inventory; transported activation files have a separate scoped identity. Hashes protect
integrity but do not prove semantic truth, human authorship or runtime binary identity.


### Review contract refactoring R2 (2026-09-14)

During refactoring, `partial-qualification-manifest` and `partial-review-publication` accept
only 1.1. Publication evidence is mandatory, including an explicit recorded/unrecorded
Workbench state. Legacy serializers and defaulted version markers are removed.

`partial-qualification-campaign` is current-only 2.0. The former schema 1.0/1.1/1.2 selection
based on available review material is replaced by the independently validated
`review_evidence.kind`: `external_suites`, `atlas_publication`, or `archived_handoff`.
These are current functional input modes, not compatibility levels or release grades.
The exact frozen inventory and semantic bindings must agree with the declared kind; a
missing archive never changes the evidence level. All modes use the same current writer
and reader; Handoff and publication validation share the existing source/evidence replay.

Old artifacts remain unchanged historical files; no migration, hash alias or upgrade on
read is provided. This supersedes the earlier Slice-7/Slice-4 reader-window decisions for
these three families only. R1's current-only policies and the future generic Stable policy
remain unchanged. Other families are left to R3/R4.
