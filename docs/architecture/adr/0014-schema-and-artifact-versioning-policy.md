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

The project-wide compatibility phase is explicitly `REFACTORING`. During this phase there is no general backward-compatibility obligation for obsolete intermediate schemas. All concrete readers and writers must accept only their current schema: `readable == (current,)`. This is enforced when constructing/registering policies and at active family boundaries. Unsupported or incorrectly typed markers fail clearly.

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


### Assertion qualification contracts Slice 7A (2026-09-15)

`assertion-golden-suite` and `assertion-qualification-report` are current-only schema-1 families
during the refactoring phase. Golden suites are independently persisted review/qualification truth
and carry semantic resource identity through explicit ontology-version references. Qualification
reports bind the normalized golden-suite hash and every evaluated proposal hash, but do not embed
acceptance thresholds or adoption authority. Development and Holdout use the same schema while
remaining different suite partitions.

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

### Remaining concrete compatibility removal R3 (2026-09-14)

The historical reporting windows listed above are superseded for current execution:
`cascade-provenance` is 1.6 only, `qualification-matrix-report` 1.1 only,
`qualification-consensus` 5.0 only, `engineering-document` 1 only,
`context-adoption-batch` 1 only, and `qualification-matrix-manifest` 1.6 only.
Direct models, repository and model-catalog entry points, recognized embedded artifacts,
replay, history and qualification consumers reject obsolete/missing markers. Document
inventories do not silently skip unsupported sources. There is no automatic v8 upgrade or
fingerprint-preserving old serializer. Human authority and explicit observation availability
are independent of serialization age and remain protected.

Only schema markers change in the four older shipped matrix manifests. Matrix/prompt/model/
resource identities and qualification thresholds are not revised. Historical raw data in a
current contract remains historical, not fresh confirmation or evidence of Holdout independence.
The generic Stable-phase policy remains untouched; global phase/inventory guards belong to R4.


### Global enforcement R4 (2026-09-14)

All 57 registered families now have enforced current-only policies. No concrete schema
version changes in R4. Generic Stable tests explicitly opt into a synthetic Stable phase;
a Stable policy cannot widen an active Refactoring family. Marker types are exact to avoid
Python's boolean/integer/float equality from accepting a different serialized type.

The separate executable `schema.bindings` inventory maps families to opt-in model guards,
actual dictionary-envelope writers and shipped resource patterns without importing adapters
into the core. Architecture tests check complete coverage and current defaults. Shared model
serialization checks actual copied/constructed values, not a registry-derived substitute.
Dictionary guards precede publication and do not normalize payloads or arbitrary attachments.

Unexpected Atlas schema warnings fail tests. Old baseline API aliases are removed. Synthetic
end-to-end tests retain source-bound MCP suggestions, human Web decisions, independent Holdout
membership and archived Handoff evidence through campaign preparation. No warning suppression,
new compatibility layer, implicit confirmation, automatic migration or relaxed quality gate is
introduced. See the [R4 guide](../../user-guide/schema-refactoring-guards.md).

### Lifecycle schema discovery R5 (2026-09-14)

R4's binding checks are extended from the then-registered families to discovery of the
serialization markers that actually exist in source. Class-level `schema_version` markers and
raw JSON/YAML envelope markers are inventoried independently. Every discovered marker must be
owned by a central `SchemaPolicy` family or have an explicit local/embedded classification with
a reason. Adding an unclassified marker therefore fails the architecture suite even when no
registry entry was added for it.

Lifecycle-crossing contracts found by this discovery are registered current-only for the active
`REFACTORING` phase. This includes previously local pipeline metadata, qualification/run
metadata, workflow checkpoints, evaluation envelopes and other independently read artifacts.
Reader and writer boundaries validate the explicit current marker instead of defaulting,
normalizing or transparently projecting an obsolete persisted schema. In particular, the
current applicability golden corpus is schema 3.0 and the current applicability prediction
snapshot is schema 2.0; prediction schema 1.0 is no longer projected automatically on read.
The dedicated, explicitly invoked golden-corpus migration remains separate from normal reader
compatibility.

The source inventory distinguishes lifecycle contracts from genuinely embedded or temporary
records. Local exceptions are therefore reviewable architecture decisions rather than gaps in
the registry. The generic future `STABLE` reader-window policy is unchanged.


### Assertion-centred semantic core reset (2026-09-14)

The active refactoring treats `.atlas` and `local` as disposable generated workspaces. The
EngineeringDocument persistence contract therefore restarts at integer schema **1** and is
current-only. No schema-8/9 reader, migration or compatibility fixture is retained for this
reset. `DocumentKnowledge` is an embedded schema-1 contract owned by EngineeringDocument; it
does not create an independent persistence family. Schema 1 remains the marker for the new
canonical core until a deliberate future compatibility decision requires another revision.
