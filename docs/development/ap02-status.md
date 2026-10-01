# AP02 status — Series A / S01-S02

Date: 2026-10-01.

## Scope

Series A implements only AP02-S01 and AP02-S02. Productive extractor/parser/verifier output is not
cut over. No context is retrofitted into v8 review snapshots, no ontology is extended and no real
model/verifier/cascade/embedding execution is part of this series.

## S01 — inventory, contract and AP01 protection

The supplied snapshot SHA-256 is
`fb646ddeb1cef1c9899461aff5311868e386174f753b0b3ff991ba18a559bad8`, matching the AP02 planning
basis. `docs/development/ap01-status.md` reports AP01 S01-S10 complete and defines the frozen v8
handover. The snapshot itself does not contain the private completed audit/golden/report files under
`local/review/...` and `local/evaluation/...`; only `local/README.md` and `local/sources/.gitkeep`
are present. Their contents were therefore not reconstructed.

`docs/development/structured-context-evidence.md` records the Series-A source contract, consumer
matrix and initial technical reference cases. The historical `FrozenSourceResolver` remains bound
only to source surfaces embedded in the AP01 audit. No current EngineeringDocument fallback was
added to that path.

Before implementation, the AP01 synthetic/offline baseline was run with the already installed
system Python because `uv run` could not resolve missing packages without network access:

```text
python -m pytest -q \
  tests/integration/assertion_qualification/test_offline_regression_pipeline.py \
  tests/architecture/test_assertion_qualification_boundary.py \
  tests/unit/application/assertion_qualification/test_assertion_review_audit.py
55 passed
```

The attempted equivalent `uv run pytest ...` was not a test result: `uv` tried to fetch `ruff` from
PyPI and failed because the execution environment has no network access.

## S02 — source surfaces and heading origin

Series A adds an application-layer, transport-neutral source-surface resolver with explicit current
document binding, source revision, clause/surface identity, origin, availability and access state.
It resolves canonical body/heading excerpts without normalization and exposes existing table/formula
objects only through bounded media handles. No network or implicit edition lookup exists.

Heading origin uses existing clause attribute provenance. Normalized content enrichment now records
a detected source heading even when it equals an existing AtlasData fallback. Synthetic part-root
labels are marked explicitly and therefore cannot be mistaken for original source headings.

The resolver is deliberately separate from AP01's frozen audit resolver and is not yet wired into
the extractor, verifier, cascade, MCP or evaluator. Those cut-overs remain assigned to later AP02
slices according to the consumer matrix.

## Contract identifiers and schema impact

- source-surface contract: `source-surface-resolution-v1`;
- source-revision contract: `engineering-document-source-surfaces-v1`;
- existing assertion CBox remains `1.3`;
- existing AP01 evaluation contract remains `assertion-clause-local-v1`;
- no persisted schema family or schema version changes are introduced in Series A.

## Next work

Series B starts with S03/S04 only after the locally applied Series-A delta passes the user's `ruff`
and full `pytest` checks. It may build structural candidates and selection policy on the resolver,
but must not reinterpret the frozen AP01 snapshots.
