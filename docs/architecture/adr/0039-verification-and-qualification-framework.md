# ADR-0039: Verification and Qualification Framework

## Status

Accepted

## Context

Standards Atlas transforms standards through several deterministic artifact layers. A large
number of unit and integration tests already protect individual implementations, while the
golden corpus established by ADR-0034 protects extraction and normalization regressions.
However, the project still lacks a single verification model that explains which evidence is
required at each boundary, how adapter implementations demonstrate substitutability, and how
qualification results are persisted for later review.

A simple coverage target is insufficient. High line coverage can coexist with untested domain
invariants, incompatible adapters, accidental nondeterminism, or workflow failures. Conversely,
slow tests that require Docling, Doorstop, private PDFs, or complete catalogs must not make the
fast developer feedback loop unreliable.

## Decision

Standards Atlas adopts a layered verification and qualification framework with five test
classes:

1. **Unit tests** verify deterministic rules, value objects, services, and isolated mappings.
2. **Contract tests** define observable behavior required from implementations of application
   ports and repositories. Every new adapter must pass the relevant shared contract.
3. **Property tests** generate many valid inputs to challenge stable invariants such as
   serialization round-trips, identity preservation, path containment, and deterministic
   ordering.
4. **Integration and workflow tests** verify assembled boundaries, real persistence formats,
   CLI compatibility, and orchestration behavior. External runtimes are explicitly marked.
5. **Qualification tests** execute versioned corpora and persist reviewable evidence including
   tool version, environment, Git identity, corpus identity, artifact hashes, case results, and
   failures.

Pytest markers identify tests whose execution policy differs from the default suite:
`contract`, `property`, `qualification`, `docling`, and `doorstop`. The normal `pytest` run
continues to execute all available tests; markers also allow focused local and CI stages.

Hypothesis is the standard property-testing library. Generated examples must be bounded,
reproducible by Hypothesis, and focused on contract-level invariants rather than implementation
internals.

The command

```bash
uv run standards-atlas qualification golden-corpus
```

executes the checked-in golden corpus and writes JSON and Markdown reports below
`.atlas/qualification/runs/`. A failed qualification still writes its evidence and then exits
with a non-zero status. Reports are derived artifacts and are not silently used to update
expectations.

## Verification rules

- Tests assert public behavior and artifact contracts, not private call sequences.
- Bug fixes add the smallest test that reproduces the defect at the lowest meaningful layer.
- A contract change requires an ADR or an amendment to the governing ADR plus reviewed fixture
  changes.
- Golden files are never regenerated merely to make tests pass.
- Deterministic outputs are compared byte-for-byte where byte stability is part of the contract;
  semantic invariants are used where multiple serializations are intentionally equivalent.
- External dependencies, network access, local copyrighted data, and GPUs are not prerequisites
  for the deterministic core suite.
- Qualification reports identify evidence; they do not claim statistical completeness or
  certification by themselves.

## Consequences

- Adapter substitutability becomes executable rather than assumed.
- Broad input spaces can be checked without maintaining large enumerated fixture sets.
- Qualification runs produce durable, reviewable evidence instead of transient console output.
- Test markers support fast feedback and explicit dependency-aware CI stages.
- Property tests and corpus maintenance add review effort, but failures expose contract gaps that
  example-based unit tests often miss.
