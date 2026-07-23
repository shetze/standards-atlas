# ADR-0031: Deterministic Transformation Ledger

## Status

Accepted

## Context

The normalized document contract preserves source and layout evidence, but provenance alone does not explain why an observation was removed, combined, repaired, or interpreted as a different structure. Statistics report aggregate counts and diagnostics report exceptional conditions; neither provides a replayable, item-level account of ordinary deterministic transformations.

This gap became visible while correcting page furniture, caption ownership, visual assets, and list hierarchy. A reviewer must be able to distinguish the source observation, the applied rule, and the resulting normalized item without reconstructing the normalizer's control flow from code.

The ledger must not compromise deterministic serialization. Runtime timestamps, machine identifiers, and execution-specific data therefore cannot be part of the normalized payload.

## Decision

`NormalizedExtractedDocument` contains a `TransformationLedger`. Its ordered `TransformationEvent` entries record:

- a stable event identifier derived from the canonical event payload;
- the normalization stage and rule identifier;
- the performed action;
- source item identities;
- output item identities where an output exists;
- a concise rationale;
- deterministic rule-specific details.

The initial ledger covers:

1. content selection and page-furniture suppression;
2. mapping from extracted observations to normalized item types;
3. inter-item and intra-item hyphenation repair;
4. merging adjacent prose fragments;
5. creation and merging of logical lists.

Events describe applied transformations only. Disabled rules and rejected candidates are not emitted as events; exceptional or ambiguous conditions remain `NormalizationIssue`s. Aggregate metrics remain in `NormalizationStatistics`.

Event identifiers use the first 16 hexadecimal characters of a SHA-256 digest over canonical JSON containing all semantic event fields. They are stable across runs and independent of event order, timestamps, and item sequence numbers.

The ledger is embedded in the deterministic document artifact and covered by its content hash. Run metadata remains separate.

## Consequences

A normalized artifact can explain each material transformation without consulting transient logs. Regression tests can assert rule application and provenance directly. Downstream review tools can link normalized structures to transformation events.

The document payload becomes larger because ordinary mappings are recorded. This is accepted in favour of complete traceability. A future compact serialization may deduplicate repeated rule metadata without changing the logical contract.

Intermediate output identities may appear in events when later stages merge or replace those items. They are deterministic transformation-local identities, not promises that every output remains a final top-level item. Source lineage remains the durable bridge across stages.

The normalized document schema version is increased to 8.

## Alternatives considered

### Store only aggregate statistics

Rejected because counts cannot explain individual transformations.

### Write a separate timestamped log

Rejected because it would not be content-addressed with the normalized artifact and would make deterministic comparison harder.

### Record only lossy transformations

Rejected because structural reinterpretations such as list creation and text merging are equally important for review and debugging.

### Store implementation function names

Rejected because function names are unstable implementation details. Explicit rule identifiers form the durable contract.
