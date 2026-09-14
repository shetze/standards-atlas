# Schema refactoring R4 — validation

## Input and scope

Input: `standards-atlas-current-202609140808.zip` (snapshot comment
`ed03b77ab06f7a5ee1e6dbee0a0fc7b9fee1d54a`). The implementation is based on this
combined R1/R2/R3 and complete review/Handoff snapshot. Earlier patch ZIPs are not overlaid.

The change set adds global Refactoring policy enforcement, type-exact markers, actual
model/envelope writer guards, executable schema-boundary coverage and cross-boundary
regression. All 57 existing `(current, readable, location)` registry entries are identical
to the input snapshot. No resource, prompt, model, threshold, data or artifact-format
version changes, compatibility migration or productive execution are included.

## Automated checks

The delivery contains **59 new or changed files** (51 modified, 8 new), relative to the
project root. All **1,467 untouched snapshot files** remain byte-identical; no files are
deleted. The ZIP contains no production corpus, review decisions, generated test data,
virtual environment, caches or Git metadata.

| Check | Result |
| --- | --- |
| Full pytest run on snapshot + applied ZIP, no excluded directories | **3,564 passed, 14 skipped, no warnings** (229.71 s) |
| Independently freshly extracted snapshot + ZIP: architecture, schema, R1/R2/R3/R4 regressions | **713 passed, no warnings** (16.45 s) |
| Dedicated R4 cases (included in both runs) | **294 passed** |
| All 57 registry versions, reader windows and artifact locations versus input | Identical |
| 35 models × validation/serialization JSON Schema | All **70 comparisons identical** |
| Current-artifact experiment below | **4 model serializations identical; 42 files unchanged** |
| Python syntax/compilation, new line lengths, whitespace and 39 local Markdown links | Passed |
| ZIP integrity and original/changed-file byte comparison | Passed |

The 14 skips are: Docling integration (1), missing Hypothesis (1), missing optional MCP
SDK/transport (4), private Run-074 fixtures (2), and opt-in Chromium tests (6). In particular,
this environment does not exercise the Docling/PyTorch path that emitted warnings in the
user's earlier run. The warning policy does not suppress those third-party warnings.

The full run includes the complete review/Handoff regression as well as R1–R3. The
independent targeted run uses:

```bash
pytest -q tests/architecture tests/unit/application/schema \
  tests/unit/application/test_schema_baseline.py \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_review_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_schema_refactoring_r3.py \
  tests/unit/application/semantic_qualification/test_schema_refactoring_r4.py
```

The dedicated R4 files contain 294 parametrized cases:

| Area | Cases |
| --- | ---: |
| Executable registry/model/writer/resource architecture inventory | 71 |
| Current-only policies, JSON inputs and actual model serialization | 183 |
| Actual projection/extraction envelope writes and raw reads | 32 |
| Synthetic end-to-end review plus failure-before-write boundaries | 8 |

These overlap with the full and targeted runs; counts must not be added to the full suite.
Existing synthetic Stable tests now opt in explicitly. R2/R3 registry-drift tests use
valid current-only replacement policies and allow rejection at earlier guarded model
boundaries; their output-preservation and rejection assertions remain in place.

The end-to-end regression follows a synthetic corpus through history indexing, budgeted
selection submitted via registered typed MCP functions, model-only annotation/evidence
proposals, blind Holdout Web review with an explicit recorded assessment/reveal, confirmed
human values, atomic Handoff, campaign preparation, model-free planning and the final
archive containing a replay-verified nested review ZIP. It checks unchanged Holdout
membership, no automatic human decisions, preserved negative/empty values, source and
exposure bindings, and no activation without independent qualification evidence.

## Current-artifact preservation experiment

A separate pristine copy of the uploaded snapshot created a synthetic completed review,
publication, Handoff and schema-2.0 campaign. R4 loaded and verified that Handoff and
campaign against unchanged resources. The package, state, publication and campaign model
JSON serializations are byte-identical to those produced by the input implementation.
All 42 files recorded before verification remain byte-identical. In a separate comparison,
all 35 bound models produce identical validation and serialization JSON Schemas to the
input implementation (70 comparisons). The permanent architecture regression requires the
shared wrap serializer to preserve its delegated output properties instead of replacing
them with an unconstrained Any/dict schema. These are synthetic current-format artifacts,
not a migration or a production-data compatibility claim.

## Scope and limitations

Python 3.13.5 and pytest 9.0.2 were used. The full run has no excluded test directories.
Optional dependency/private-fixture/browser skips are reported separately. No external
LLM call, productive qualification or actual human annotation was performed.

The new end-to-end test uses Starlette's TestClient for the real ASGI routes and calls
registered MCP tool functions through a registration double. It is not a live MCP SDK
transport, Codex session, browser-engine or authenticated-reviewer test.

Ruff was not installed. Installation attempts through the configured index and public
PyPI failed; direct binary/wheel downloads were also unavailable. Therefore no successful
Ruff run is claimed. Import ordering, new line lengths, Python syntax and whitespace were
checked separately; these checks are not a substitute for the full Ruff ruleset.

Generic Stable-window support is tested using explicitly synthetic policies. It cannot
reopen concrete Refactoring reader windows. Default construction of new Python models
is distinct from serialized JSON reads and explicit envelope validation. Unknown/local
implementation markers and opaque archive attachments are not inferred to be new central
contracts. Existing domain, source, semantic and publication checks retain their authority.
