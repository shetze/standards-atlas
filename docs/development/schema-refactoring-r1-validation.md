# Schema refactoring R1 — validation record

## Scope and source

Implemented against the supplied `standards-atlas-current-202609140446.zip`, archive
commit identifier `9c65501d68fd3668848ba4495b2293a37050e97c`.
Source ZIP SHA-256: `8086ba19ad327d12e22f49c3f366d37cc33e2d6edd675455891ebc3234b64985`.

Only the `partial-request-plan`, `partial-semantic-observation` and
`partial-cascade-report` schema families are made current-only in R1. Their current
version remains 1.1. The change does not globally enforce the Refactoring policy on
other families, migrate archives or change semantic/model/prompt/quality decisions.

**Source-state finding:** the supplied ZIP contains the Slice-3 review workbench, but
not the Slice-4 review handoff/archive modules. This patch uses the uploaded snapshot
as its baseline and does not silently apply the earlier Slice-4 ZIP. It is not a
cumulative replacement for Slice 4. Subsequent refactoring must use the actual merged
project state rather than overwrite shared files with an older patch.

## Completed checks

| Check | Result |
| --- | --- |
| Architecture and unit test directories | 2,734 passed; 10 skipped; 199 warnings from other schema families |
| Integration, contract and property test directories | 172 passed; 4 skipped |
| Final dedicated R1 regression file | 79 passed; no warnings |
| Fresh snapshot + ZIP: architecture, schema policy and affected partial paths | 329 passed; no skips or warnings |
| Python syntax, diff whitespace, local documentation links and ZIP integrity | Passed |
| Source-file preservation | All 1,483 unmodified input files are byte-identical |

The test groups overlap and must not be added together. The broad run includes the
first 74 R1 cases; five additional archive/history/focused-reader cases were subsequently
added and are included in the final 79-case run. The final packaging check reruns the
completed regression file and the relevant surrounding tests against a newly unpacked
snapshot with the ZIP applied, with R1 schema warnings treated as errors.

The remaining broad-run warnings belong to `partial-qualification-campaign` and
`qualification-matrix-manifest`. No warning from any of the three R1 families occurred.
No global warning suppression was added. The new regression file treats any unexpected
warning from those three families as an error.

## Covered boundaries

- All six supported prompt variants share schema-1.1 plans/observations while retaining
  distinct request fingerprints and their existing carry capabilities.
- Version markers are mandatory in direct Python/JSON model validation and nested plans;
  old/future/mistyped/missing markers and invalid model-copy instances are rejected.
- Source/selected-question/accepting-state bindings and explicit false/null/empty values
  remain intact. Carried decisions never become fresh model observations.
- Current same-contract resume and offline failed-response revalidation remain supported.
  Obsolete artifacts cannot be upgraded or silently rebound by either path.
- Writer policy drift and obsolete observation publication fail before publishing the
  corresponding contract. Existing output bytes remain unchanged in rejection tests.
- Report mode and effective configuration are checked before a resumed run can replace
  the report; replay always validates presentation metrics, with no schema-1.0 fallback.
- Planned completion remains null and is not measured zero. Both planned and executed
  archives can be read-only audited under the current contract.
- Cascade replay, diagnostics, review history and focused physical-budget readers cannot
  accept obsolete partial plans/observations as evidence.

## Environment and limitations

Tests ran under Python 3.13.5 with synthetic local sources and fake gateways, not a
productive corpus or live LLM/Codex session. Optional MCP/Docling/Hypothesis/browser or
private-fixture checks may be skipped in this environment; skips are not passes.

Ruff was not installed. An attempt to install Ruff and Hypothesis failed because
`pypi.org` could not be resolved. Python compilation, diff whitespace and a supplemental
AST/line-length review were performed, but are not represented as a successful Ruff run.

No human annotations, canonical corpus data, qualification thresholds, release gates or
existing archives were modified. See the [R1 usage note](../user-guide/partial-schema-refactoring.md)
for regeneration and current-contract resume behavior.

## Patch packaging

The ZIP contains 19 root-relative files: 15 replacements and four additions. No deletions,
model resources, private data, caches, generated test artifacts or dependency files are
included. ZIP members are byte-compared with the reviewed source tree, and all unaffected
members are compared with the original snapshot. The 329-case check runs in the fresh
extraction rather than relying on an installed copy of the project.
