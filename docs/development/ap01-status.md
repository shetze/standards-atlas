# AP01 status — Series A / S01–S03

Date: 2026-09-27. Implementation and execution-environment tests complete;
user-local `uv run ruff check .` / `uv run pytest` verification is still pending.
Only Series A is implemented. Do not treat the interim report as AP01 completion.

## Delivered boundaries

S01: byte-bound complete audit loader, duplicate-key rejection, immutable copies,
validated expected references/spans, deterministic source and raw-snapshot hashes.
S02: clause-local golden publication, unchanged confirmed IDs/values, shared native
projection, distinct clause/document/coverage counts, updated policy and schema consumers.
S03: `assertion-evaluate --review`, explicit candidate/source modes, exact audit/golden
binding, raw diagnostics retained, missing-versus-empty handling and model-free CLI tests.
The policy rejects review reports as auto-adoption qualification evidence.

Contract: `assertion-clause-local-interim-v1`. Schema families remain at 1, without
legacy document-wide readers. Full contract: `assertion-golden-regression.md`.

## Actual checks

S01: 76 tests passed. S02: 527 passed. S03 gate: 543 passed.
Final targeted assertion/CLI/architecture/schema set: 544 passed.
Final full suite: 2064 passed, 7 skipped (Docling, Hypothesis, MCP and two existing
private run-074 checks unavailable). Runtime: CPython 3.13.5; project constraint unchanged.
Ruff could not be executed: the package/binary is absent and package-index access failed.
This is an outstanding lint check, not a lint pass. Delivery test logs give the commands.

The real private audit was retrieved byte-identically to the detail plan's hash.
Golden: 20 cases, 9 documents, 51 entities, 24 assertions. Candidates: all 20
snapshots, 60 entities, 15 assertions. Confirmed IDs, labels, classes, objects,
normative force and all span offsets were compared without modification.
Publication/evaluation via CLI repeated in fresh processes with identical output bytes.
No extractor, verifier, cascade, embedding or other model was executed.

Private artifacts remain under `local/review/assertions/assertion-pilot/0.1.0/`
and `local/evaluation/assertions/assertion-pilot/0.1.0/`, not in public fixtures.
`local/` is generally ignored; preserve or attach the audit separately for the next series.

## Next authorized implementation boundary

After the user's local checks, start Series B (S04–S06) against the resulting snapshot.
Replace interim typed/bucket matching with separate strict and diagnostic matching;
implement ambiguity and duplicate handling, dimensional supports/null denominators,
and the frozen-source resolver with source-surface-aware evidence comparison.
Do not change the audit, saved candidates, confirmed expectations or productive context policy.
Work-product metrics and semantic findings remain Series C; final AP01 baseline is Series D.
