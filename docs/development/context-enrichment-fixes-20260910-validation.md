# Context-enrichment fixes: validation record, 2026-09-10

## Inputs and scope

Implementation base: `standards-atlas-current-202609100800.zip`.
Offline comparison corpus: `context-20260910T025523849669Z-7ead9437.zip`.
The archive supplies 26 documents and 5,712 clause/structure records. Its original
run reports contain 2,700 candidates, 2,611 successful attempts and 89 failed
attempts. None of these archived outcomes was rewritten.

All three slices are cumulative. No new LLM invocation was made, no rejected
answer was imported, and the baseline archive and input snapshot are unchanged.
The accompanying JSON provides baseline details and source archive hashes.

## Completed automated tests

Python 3.13.5, final cumulative implementation:

```bash
python -m pytest -q tests/unit tests/architecture
```

Result: **1,651 passed, 3 skipped**, four existing schema-deprecation warnings
(qualification-matrix manifest 1.5 versus current 1.6).

```bash
python -m pytest -q \
  tests/integration/atlasdata \
  tests/integration/workflows/test_context_scope_transport.py \
  tests/integration/workflows/test_information_routing_pipeline.py \
  tests/integration/workflows/test_enrichments_end_to_end.py \
  tests/contract
```

Result: **98 passed**. These selections are disjoint from the unit/architecture
run: **1,749 completed passing tests in total**, plus three skipped tests.

`git diff --check`, source compilation and the changed-file line-length check
also passed. An earlier unfiltered `pytest -q` attempt did not complete within
the execution limit; it is not represented as a full-suite pass. Ruff and mypy
were not run. Ruff was unavailable in the execution environment. The two
completed selections above, not a claim about every optional test or tool,
define the automated-test scope of this record.

## Slice 1: exact, allowlisted ID completion

Against all 26 original documents, the final cumulative implementation fills
**452 of 452 allowlisted single-target IDs**. Each changed edge differs solely
in `target.clause_id` (null to its exact permitted ID).

The offline check compares every full clause model, not just aggregate counts.
After restoring the original routing for comparison, all other clause fields
are identical. Within routing, scopes, roles, evidence, target text/title/key,
edge cardinality/order and all other attributes are identical. Baseline and
provenance are identical. A second repair yields the exact same document.

Unit tests cover stale source and edge hashes, conflicting or existing IDs,
wrong edition/key, ambiguous/missing targets, incomplete evidence groups,
protected routing, duplicate allowlist entries and absent source edges. CLI
tests verify no model startup, dry-run byte preservation, exact original-byte
backups, mandatory write reports, report-path guards, write idempotence and
unchanged original run ledgers.

The supplied allowlist deliberately excludes the 34 multi-target candidates in
the initial analysis. It is not permission for general semantic routing repair.

## Slice 2: numerical false positives and retry behavior

An isolated scientific-number comparison removes **1,368 bare false reference
mentions in four clauses**, with every other mention and source offset intact:

| Source | Mentions before | After | Removed |
| --- | ---: | ---: | ---: |
| EN 50126-2:2017 E.2 | 3 | 2 | 1 |
| IEC 61508-6:2010 B.3.3.3 | 1,330 | 4 | 1,326 |
| IEC 61508-6:2010 B.4.4.2 | 125 | 85 | 40 |
| ISO 26262-11:2018 D.1 | 43 | 42 | 1 |

This is 20 more than the initial analysis's 1,348 complete number matches: the
additional removed mentions are partial `0.0e` matches inside complete `0.0e+0`
numbers. All removed spans are inside scientific numeric tokens; none had a
resolved target ID. The rule does not filter explicit labelled citations.

For B.3.3.3 the reconstructed user prompt shrinks from **488,398 to 24,422
characters**, with the full source clause retained. These are character counts,
not a new model token measurement. The numerical fix alone leaves 5,708 input
fingerprints unchanged.

Gateway/service tests prove that a direct typed context-limit error makes one
request, preserves failure status and provider token/context counters, and does
not trigger a larger retry. A truncation followed by a context-limit error makes
two requests, retains both causes in order, and skips the invariant retry.
Ordinary truncation retains its prior bounded retry. Generic HTTP 400 errors are
not reclassified as context-limit failures.

## Slice 3 and cumulative parser checks

The dedicated bounded-parser module has **34 passing tests**, including exact
edition commas, repeated matching object-range labels and labelled multi-letter
object coordinates. Negative cases cover wrong editions, object/clause
namespace collisions, incomplete groups, mixed-kind, reversed, cross-parent or
oversized ranges, and unlabelled multi-letter coordinates.

Across the baseline, **11,602 previously resolved query occurrences** preserve
the exact ordered target IDs under the final resolver:

| Query source | Unchanged resolved occurrences |
| --- | ---: |
| Extracted reference mentions | 3,925 |
| Routing reference edges | 3,772 |
| Scope reaches | 3,905 |

The check counts occurrences, not distinct target clauses. It also records 15
newly parseable query occurrences. Nine archived failed responses belonging to
the planned syntax classes now pass transport validation in an offline replay.
**This is not semantic approval or nine newly successful enrichment attempts.**
Zero rejected responses were persisted; informational-scope safeguards were not
weakened.

## Cumulative input compatibility

The original archived request builder and final request builder were compared
for all 5,712 clause/structure records, with their respective extracted/indexed
references and identical static source/catalogue content. Cached static catalogue
fingerprints were used to avoid recomputing identical document content for every
clause; no model output was involved.

**5,695 input fingerprints remain identical; 17 change**: the four numerical
cases plus 13 parser-related source cases. The JSON records each affected clause.
This checks input compatibility, not a claim that all 5,695 records were prior
successful enrichment candidates. No global `--fresh` invalidation is required.

## Verification limits and safe application

These are offline structural/behavioral regression checks against the supplied
baseline, not an assertion of absolute regression freedom or achieved model
success rates. Fresh model behavior, latency savings and aggregate end-to-end
success rates have not been measured. No scope semantics were relaxed, no
missing standard parts were added to manifests, and no global token budget was
increased.

Installing the changed files does not execute the 452-ID repair. Use the
[documented ID-only dry run](../user-guide/context-enrichment-baseline-fixes.md),
review its report, then explicitly write with a separate report if appropriate.
Preserve the original archive and checksum-bound resume receipt. Repair changes
canonical checksums; it must not masquerade as the original frozen baseline.
