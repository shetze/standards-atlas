# Schema refactoring R3 — validation record

## Baseline and scope

Implementation baseline: `standards-atlas-current-202609140712.zip` (the supplied,
merged R1/R2 and Review Slice-4 snapshot).

Source ZIP SHA-256:
`67d44e40de73ef0c149b86b6ce15873c0fa6128af82d09fd5b512a5055b1feb8`.

Only the six R3 policies change in `SCHEMA_POLICIES`:

| Family | Sole readable/writable schema |
| --- | --- |
| cascade-provenance | 1.6 |
| qualification-matrix-report | 1.1 |
| qualification-consensus | 5.0 |
| engineering-document | 9 (integer) |
| knowledge-adoption-batch | 1.1 |
| qualification-matrix-manifest | 1.6 |

The other 51 policies are unchanged. The generic Refactoring/Stable policy,
R1/R2 models and the Handoff/publication/review contracts are not revised.
No public AtlasData grammar, prompt text, model selection or acceptance/release
threshold is changed. Four existing matrix manifests change only their schema
marker from 1.5 to 1.6, not their resource identifiers or operational settings.

## Implementation checks

- Explicit current markers in the four Pydantic contracts, including nested validation,
  JSON input and unchecked `model_copy` instances; current-only document envelopes
  reject missing, string, float, boolean, obsolete and future markers.
- The v8 document upgrader, schema-4 consensus fingerprint serializer and omitted
  empty adoption source-requirements serializer are removed, not replaced by migration.
- Actual writers check their current registry policy before publishing. Consensus and
  adoption service entry points revalidate unchecked instances before writes.
- Full document loads, inventories, MCP clause reads, workflow output checks and
  context/corpus checkpoints cannot accept the removed document contracts.
- Direct reports and recognized named archive members are checked at replay, adoption,
  Challenger, extraction and archive creation boundaries. Schema validation does not
  rewrite archived bytes or canonical fingerprint input. Unrelated opaque attachments
  are not claimed to be semantically validated.
- Archive collection validates every recognized input before deduplication and rejects
  conflicting same-name sources, instead of hiding an obsolete/conflicting input.
- Invalid history identifies its path/member and cannot publish a candidate index or
  change package membership. Missing votes remain unobserved; explicit false/null/empty
  are not fabricated from model defaults. Current historical reports remain usable.
- Current adoption keeps confirmed human values and source requirements. An empty
  requirement list is serialized as `[]`; there is no omitted-field hash alias.

## Test evidence

The new `test_schema_refactoring_r3.py` contains **199 synthetic regression cases**.
The targeted run including extraction and workflow regressions completed with
**242 passed, no warnings**. A domain-focused review/Process/adoption/MCP run completed
with **81 passed**; these groups overlap and must not be added.

The complete available suite, including architecture, unit, integration, contract
and property test directories, was executed with `python -m pytest -q --tb=short -ra`:
**3,270 passed, 14 skipped in 345.15 s, no warnings and no failures**.
This run includes all 199 new R3 cases. No test directories were excluded.

A preceding integration/contract/property run (excluding only the unavailable Docling
directory) completed with **172 passed, 3 skipped**; it overlaps the full run and is
not additional coverage to add to its total.

The changes ZIP was applied to a newly extracted original snapshot, not to the
working checkout. Architecture, schema inventory, R1, R2, all 199 R3 cases,
Review-Handoff, document repository and workflow tests completed with
**511 passed in 98.90 s, no warnings**. No code was changed after this run.

ZIP integrity and exact member bytes were verified. The patch contains **66 files**:
61 modified and 5 new. All **1,452 unchanged source files** were byte-identical to
the original ZIP. The final validation-record update changes documentation only.

Syntax was checked with `compileall`/AST parsing. Whitespace was checked using
`git diff --check`; changed Python files were checked against the configured
100-character line limit. These are not a substitute for Ruff.

## Environment and exclusions

Python 3.13.5 / pytest 9.0.2 / Pydantic 2.13.4. All sources in the new regression
suite are synthetic. No productive model requests, qualification campaign or real
Codex session was performed.

Ruff is not installed. Its installation failed because the execution environment
could not resolve PyPI. No Ruff success is claimed. Optional MCP transport, Chromium,
Docling, Hypothesis and private Run-074 checks are only executed when their documented
prerequisites are present; actual skips are listed in the full pytest summary.

The original private Run-074 tests now assert rejection of its obsolete consensus
contract without archive/canonical/public writes. The archive was not supplied and
those two tests were skipped. The current-contract synthetic Process/adoption/
AtlasData/CBox integration remains in the normal suite and is not replaced by those
negative private tests.

## Existing data

There is no automatic migration, marker rewriting or old-fingerprint preservation.
Keep old archives and human evidence unchanged. Obsolete canonical documents must be
kept separately from a current repository and regenerated from reviewed sources before
that repository is used. A current publication is not reinterpreted as new human review.

The patch contains source, shipped configuration, tests and documentation only. It
contains no productive corpus data, model outputs, human decisions or generated archives.
