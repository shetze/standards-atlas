# Testing and qualification

Standards Atlas treats tests as executable evidence for architectural and artifact contracts.
The goal is not maximum test count or line coverage. The goal is confidence that deterministic
transformations preserve source evidence, adapters remain substitutable, persisted formats stay
readable, and complete workflows behave predictably.

The governing architecture decision is
[ADR-0039](../architecture/adr/0039-verification-and-qualification-framework.md). Golden-corpus
regression control is defined by
[ADR-0034](../architecture/adr/0034-golden-corpus-and-regression-qualification.md).

## Test layers

### Unit tests

Unit tests are the default tool for deterministic domain behavior and application rules. They
should have no network access and normally use no filesystem except `tmp_path`.

Typical subjects include:

- value-object validation and domain invariants;
- parsers, classifiers, normalization rules, and transformation decisions;
- application services with in-memory fakes;
- serialization and rendering helpers;
- workflow planning and lifecycle transitions.

A unit test should describe observable behavior. Mocking private methods or asserting internal
call order is discouraged because it makes refactoring unnecessarily expensive.

### Contract tests

Contract tests define behavior that every implementation of an application port or repository
must provide. They belong below `tests/contract/` and carry the `contract` marker.

The initial repository contract verifies:

- canonical document round-trip fidelity;
- replacement semantics for the same document identity;
- accurate existence reporting;
- explicit failure for unknown identities.

When a second implementation is added, the contract scenarios should be shared through a
factory fixture or abstract test base rather than copied and allowed to diverge.

### Property tests

Property tests belong below `tests/property/` and carry the `property` marker. Hypothesis is used
to generate bounded valid inputs and shrink failures to minimal counterexamples.

Good properties include:

- parse/serialize or save/load round trips preserve canonical values;
- artifact identity does not depend on lineage metadata;
- ordering and hashing are independent of input creation order;
- generated paths remain inside the configured workspace;
- repeated deterministic transformations are idempotent.

Do not reproduce implementation algorithms in the test. State the invariant that must remain
true for all generated inputs.

### Integration and workflow tests

Integration tests exercise real adapter boundaries, persisted schemas, catalog composition, and
CLI wiring. Workflow tests verify both planning and execution behavior, including review gates,
artifact reuse, overwrite policies, and run reports.

Tests requiring installed external runtimes use explicit markers:

- `docling` for the Docling runtime;
- `doorstop` for the Doorstop CLI.

Small checked-in adapter-native fixtures are preferred over private PDFs. Tests must never depend
on copyrighted files below `local/`.

### Qualification tests

Qualification tests execute fixed, versioned evidence sets. The golden corpus under
`tests/golden_corpus/` combines byte-exact snapshots with semantic invariants for extraction and
normalization edge cases.

Run the qualification command with:

```bash
uv run standards-atlas qualification golden-corpus
```

By default, reports are written to:

```text
.atlas/qualification/runs/<timestamp>-<corpus-hash>/report.json
.atlas/qualification/runs/<timestamp>-<corpus-hash>/report.md
```

The JSON report is intended for automation and archival. The Markdown report is intended for
human review. Both include corpus identity, environment and Git information, case hashes, and
failure details. A failing corpus still produces both reports before the command exits with
status 1.

Use `--corpus` to select another versioned corpus and `--output` to place reports in a dedicated
CI artifact directory.

## Execution profiles

Run the complete locally available suite before committing:

```bash
uv run ruff check .
uv run pytest
```

Useful focused runs are:

```bash
uv run pytest tests/unit
uv run pytest -m contract
uv run pytest -m property
uv run pytest -m qualification
uv run pytest -m "not docling and not doorstop"
```

A CI pipeline should separate fast deterministic verification from dependency-aware stages:

1. lint and static checks;
2. unit, contract, and property tests;
3. integration and workflow tests;
4. optional Docling and Doorstop runtime tests;
5. golden-corpus qualification with archived reports.

Coverage is a diagnostic signal, not a release criterion by itself. New or changed contracts
must be covered at their boundary even when surrounding lines already count as covered.

## Change rules

Every defect fix should add a regression test at the lowest layer that fully reproduces the
problem. Add a higher-level workflow or corpus case only when the defect crossed an artifact or
adapter boundary.

A transformation change should include fixtures that demonstrate both the intended correction
and preservation of unrelated source evidence. Never update golden outputs solely to make a test
pass. Inspect the semantic diff and document intentional contract changes.

Review test changes with the same rigor as production changes:

- Does the test fail for the defect or missing behavior?
- Does it assert the contract rather than the current implementation?
- Is the fixture minimal and legally safe to retain?
- Is nondeterminism controlled?
- Does a snapshot change correspond to an approved contract change?
- Would the failure message help diagnose a regression?
