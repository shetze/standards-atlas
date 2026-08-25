# Test strategy and qualification

Standards Atlas treats verification as executable evidence for architectural contracts and for the
traceability of protected engineering content. The objective is not the largest possible test
count. The objective is a controlled argument that transformations are deterministic, source
evidence is preserved, persisted artifacts remain readable, adapters are substitutable, and a
complete workflow fails safely.

The governing decisions are
[ADR-0039](../architecture/adr/0039-verification-and-qualification-framework.md) and
[ADR-0034](../architecture/adr/0034-golden-corpus-and-regression-qualification.md).

## Quality risks

Testing is prioritised by the damage a defect can cause:

| Priority | Risk | Required evidence |
| --- | --- | --- |
| P0 | Loss, corruption, or misassignment of source evidence | domain invariants, round-trip contracts, golden corpus, workflow regression |
| P0 | A reviewed or published artifact is silently overwritten or downgraded | lifecycle unit tests and persisted integration tests |
| P1 | A transformation is nondeterministic or cannot be reproduced | property tests, stable hashes, fixed seeds, qualification metadata |
| P1 | An adapter violates a port contract or changes a persisted schema | reusable contract tests and compatibility fixtures |
| P1 | A workflow bypasses review gates or reuses stale artifacts | workflow tests at planning and execution level |
| P2 | CLI, reports, diagnostics, or configuration mislead the operator | CLI tests, report snapshots, configuration boundary tests |
| P2 | Optional runtimes make deterministic verification unavailable | isolated extras, explicit runtime markers, separate CI jobs |

Every defect fix must add a regression test at the lowest layer that reproduces the observable
failure. Add a higher-level test only when the defect crossed a process, adapter, or artifact
boundary.

## Test architecture

### Unit tests

Unit tests are the default for domain behaviour, deterministic transformations, parsers,
classifiers, rendering helpers, configuration models, and application services with in-memory
fakes. They must not use the network and should use `tmp_path` only when the filesystem is part of
the public behaviour.

Assertions should describe results and invariants, not private call order. Mocks are appropriate
at process, clock, network, and external-runtime boundaries; they are not a substitute for simple
fakes of application ports.

### Contract tests

Tests below `tests/contract/` define behaviour every implementation of a port or repository must
provide. They carry the `contract` marker. Repository contracts cover canonical round trips,
replacement semantics, identity, listing, explicit unknown-object failures, and schema
compatibility. New implementations must run the same scenarios through a factory fixture rather
than copy them.

### Property tests

Tests below `tests/property/` carry the `property` marker and use bounded Hypothesis strategies.
High-value properties are round-trip preservation, idempotence, order-independent identity,
workspace path containment, and invariants over generated clause/content structures. Strategies
must generate valid domain objects and avoid reproducing the implementation algorithm.

### Integration tests

Integration tests exercise real boundaries: filesystem layouts, persisted schemas, catalog
composition, CLI wiring, and adapter-to-service composition. Checked-in fixtures must be small,
synthetic or legally redistributable. Tests must never depend on copyrighted standards below
`local/`.

External runtimes are isolated with markers:

- `docling` requires the `docling` extra and its model/runtime dependencies;
- `doorstop` requires an installed Doorstop CLI.

A test marked for an external runtime must verify real integration. Behaviour that can be checked
without that runtime belongs in an unmarked unit test.

### Workflow tests

Workflow tests cover planning and execution separately. They verify review gates, stale artifact
detection, reuse versus overwrite, failure reports, cleanup, and ownership of managed subprocesses.
At least one end-to-end test should cover each supported workflow path with synthetic fixtures.

### Qualification tests

Qualification tests carry the `qualification` marker and execute fixed, versioned evidence sets.
The golden corpus under `tests/golden_corpus/` combines exact snapshots with semantic invariants
for extraction and normalization edge cases. A failing run must still emit machine-readable JSON
and human-readable Markdown reports.

Golden outputs are changed only after reviewing the semantic diff and documenting an intentional
contract change. They are never updated merely to make CI green.


LLM-assisted normalization-quality qualification is intentionally separate from golden-corpus
qualification. It may reuse a representative semantic corpus for exploratory model comparison,
but its semantic expected labels are ignored. The qualification is observational and therefore
does not constitute deterministic normalization evidence or modify golden outputs.

## Coverage model

Coverage is used to locate untested decisions, not to reward execution of trivial lines. The
project does not use one global percentage as a release claim. Instead:

- changed domain and application behaviour requires branch coverage of its decision paths;
- persisted format changes require forward-read and compatibility tests;
- bug fixes require a test that fails before the fix;
- security- and privacy-relevant boundaries require explicit negative tests;
- generated reports and public schemas require field-level assertions.

The coverage profile produces terminal and XML reports. A ratcheted CI threshold should be added
only after a stable baseline has been measured; it must never encourage low-value assertions or
exclusion of difficult modules.

## Execution profiles

The canonical wrapper is:

```bash
./tools/test/run.sh fast
./tools/test/run.sh coverage
./tools/test/run.sh qualification
./tools/test/run.sh full
```

The profiles mean:

| Profile | Purpose | External runtimes |
| --- | --- | --- |
| `fast` | pull-request feedback for deterministic code | excluded |
| `coverage` | identify untested branches in locally available code | Docling and Doorstop excluded |
| `qualification` | fixed evidence and report generation | corpus-dependent |
| `full` | developer/release verification with all configured extras | included where installed |

Direct commands remain useful:

```bash
uv run --extra mcp ruff check .
uv run --extra mcp pytest -m "not docling and not doorstop and not qualification"
uv run --extra mcp pytest -m contract
uv run --extra mcp pytest -m property
uv run --extra mcp pytest -m qualification
uv run --extra docling --extra mcp pytest -m docling
```

Pytest runs with strict marker/configuration validation and strict `xfail` handling. An unknown
marker, invalid configuration, or unexpectedly passing expected failure therefore fails the run.

## CI and release gates

Pull requests must pass linting, deterministic tests, and qualification tests. Runtime adapter
jobs are separate so an unavailable GPU, model registry, or external executable cannot hide a
failure in the core suite. During bootstrap they may be informational; before a release that
claims adapter support, the corresponding job must be required and green in a controlled runner.

A release candidate requires:

1. deterministic verification on the supported Python version;
2. all contract and property tests;
3. golden-corpus qualification with archived reports;
4. supported adapter/runtime jobs on representative infrastructure;
5. review of new skips, expected failures, snapshot diffs, and uncovered changed branches.

## Review checklist

For every changed test, verify:

- it fails for the missing behaviour or reproduced defect;
- it asserts a public contract or invariant;
- its fixture is minimal, deterministic, and legally safe;
- time, randomness, process state, and environment are controlled;
- failure output identifies the broken contract;
- a snapshot change corresponds to an approved semantic change;
- the test is placed at the lowest sufficient layer;
- no external runtime is required accidentally.

## Current improvement backlog

The current suite has broad unit coverage and useful workflow, contract, property, and golden
corpus foundations. The next improvements should be risk-driven:

1. add shared contracts when a second repository implementation appears;
2. extend property testing beyond document persistence to normalized serialization, identifiers,
   and deterministic reference resolution;
3. add explicit tests for audit-log redaction and concurrent writes;
4. create synthetic end-to-end fixtures for each workflow stop/resume path;
5. establish and ratchet a measured changed-code branch-coverage baseline;
6. make Docling and Doorstop runtime jobs mandatory on controlled release infrastructure.

## Formal semantic extraction qualification

Qualification manifests can enable `semantic_extraction_qualification`. In that case `workflow run --task qualification` appends an ontology-guided extraction qualification step after the semantic matrix. The step evaluates persisted semantic extraction artifacts for ontology conformance and confidence. Entity/relation precision, recall, and F1 remain `null` until a published extraction gold corpus is configured; missing ground truth is therefore explicitly unscored rather than inferred from existing semantic labels.
