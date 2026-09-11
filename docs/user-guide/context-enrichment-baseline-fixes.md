# Bounded context-enrichment baseline fixes

These three fixes were qualified against `standards-atlas-current-202609100800.zip`
and `context-20260910T025523849669Z-7ead9437.zip`. They do not turn baseline completion
into semantic approval and do not change archived failed outcomes.

## 1. Complete missing external IDs without changing routing semantics

Use the existing repair command's **reference-targets-only** mode for this repair.
The older general repair mode may also refresh baseline references and apply the
information-routing policy; it is not the same ID-only operation.

The supplied allowlist is
`cfg/evaluation/context-routing/reference-target-repair-20260910.json`. Its 452
entries are bound to the source clause, the full existing edge, and the expected
single target. They contain citations, IDs and hashes, not source prose. A stale
source, changed edge, missing or ambiguous target, wrong edition, existing ID or
protected routing is not overwritten. A source quotation must also substantiate
the existing target. Complete evidence lists may substantiate an already explicit
single target, but the stored edge is never expanded into a list.

From the project root, inspect a document without writing canonical data:

```bash
uv run standards-atlas document repair-context-routing EN50126-1 \
  --workspace .atlas/data \
  --reference-targets-only \
  --allowlist cfg/evaluation/context-routing/reference-target-repair-20260910.json \
  --report local/evaluation/context-routing/EN50126-1-targets-dry-run.json
```

After inspecting the report, persist using a separate report name:

```bash
uv run standards-atlas document repair-context-routing EN50126-1 \
  --workspace .atlas/data \
  --reference-targets-only \
  --allowlist cfg/evaluation/context-routing/reference-target-repair-20260910.json \
  --report local/evaluation/context-routing/EN50126-1-targets-write.json \
  --write
```

For all selected documents, first run the following dry-run loop. Add `--write`
and use `-targets-write.json` report names only for a subsequent write pass.
`set -e` intentionally stops this maintenance script on command/file errors; it
is not an enrichment `--fail-on-failure` policy.

```bash
set -e
allowlist=cfg/evaluation/context-routing/reference-target-repair-20260910.json
keys=$(python - "$allowlist" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("\n".join(sorted({entry["source_document_key"] for entry in payload["entries"]})))
PY
)
for key in $keys; do
  uv run standards-atlas document repair-context-routing "$key" \
    --workspace .atlas/data \
    --reference-targets-only \
    --allowlist "$allowlist" \
    --report "local/evaluation/context-routing/${key}-targets-dry-run.json"
done
```

All relevant target documents must be loaded in the workspace, not just the
source document. The exact baseline admits 452 ID completions; a different or
partially repaired workspace may correctly admit fewer. The 34 multi-target
candidates from the analysis are deliberately excluded.

The only changed canonical field is an allowed `target.clause_id` from null to
its verified ID. Source text, target reference/title/document key, roles,
evidence, edge count/order, scopes, baseline and generation provenance remain
unchanged. A repeated repair makes no further canonical change. No inference
server is started. Installing the patch alone does not run this repair.

Writes require a private `--report` and preserve the existing exact-byte backup
behavior (`*.before-routing-repair-<digest>.bak`). The report carries resolver
version, allowlist hash, per-edge before/after hashes, decisions and document
hashes. It must not overwrite canonical documents, the allowlist, or reserved
context run diagnostics. Use distinct dry-run and write report names to retain
both records. Existing canonical/companion schemas are unchanged.

A canonical repair changes the document checksum. An older
`--resume-after-context` receipt remains tied to its original baseline and can
therefore reject the repaired workspace. Do not edit the receipt or bypass this
checksum guard. Keep the original archive/receipt intact and use a normal
subsequent workflow invocation against the repaired state when appropriate.

## Additional unresolved-target diagnostics

Existing target rows and failure/target counters remain present. Reports add
`target_diagnostics_contract` and reason counts rather than silently treating
missing IDs as successes:

| Reason | Meaning |
| --- | --- |
| `document_reference` | Whole-document address; no clause ID expected. |
| `object_not_indexed` | Table/figure object has no exact indexed identity. |
| `target_document_not_loaded` | Referenced document is not in the loaded catalogue. |
| `edition_mismatch` | An explicitly requested edition cannot be matched. |
| `document_key_mismatch` | Stored key conflicts with the cited document identity. |
| `ambiguous_address` | Address is not uniquely resolvable. |
| `addressable_clause` | Catalogue can address the reference; no automatic mutation implied. |
| `unresolved_clause` | No more specific conservative diagnosis applies. |

A category is an addressability diagnosis, not confirmation that the edge role
or scope interpretation is semantically correct.

## 2. Scientific numbers and context-limit failures

The extractor ignores *bare* reference matches wholly inside a complete
scientific number such as `5.0E-08` or `0.0e+0`. Explicit Clause/Table/Figure and
qualified citations retain their existing handling. Source text and tables are
not truncated. The numerical rule alone removes 1,368 false mentions in four
baseline clauses without changing any other mention or source offset.

New extraction uses `reference-mention-extractor/v4`. Request metadata retain
v3 compatibility where the exact raw mention sequence equals the old grammar's
sequence, so a global version bump does not invalidate otherwise identical
inference inputs. Including the parser changes below, 5,695 of 5,712 baseline
clause input fingerprints remain unchanged; only 17 change. There is no reason
to use `--fresh` for the complete corpus just to install these fixes.

Provider errors explicitly tagged `exceed_context_size_error` or
`context_length_exceeded` become `LlmContextWindowError`. The same/enlarged
context is not sent through the invariant retry after this error. Ordinary
truncation keeps its existing bounded retry. HTTP 400 alone is not treated as a
context-limit error.

Private failure reports retain the complete ordered failure chain, including
first and last causes, rejected content, provider response and any supplied
token/context counters. A truncation followed by a context error is therefore
not diagnosed as an initial context failure. Failed status, retained previous
values and continuation of the overall baseline remain unchanged. This does
not increase the global token budget or salvage partial JSON.

## 3. Bounded parser alignment

The extractor, catalogue and scope resolver now consistently handle:

* Repeated matching object labels in ranges: `Table A.1 to Table A.11`.
* A separator comma after an exactly recognised norm edition:
  `ISO 26262-5:2018, Clause 8`.
* Labelled multi-letter object coordinates: `Table ZZ.1`.

Object identity remains distinct from an equal-numbered clause. No parent
clause or document is substituted for a missing table/figure. Wrong editions,
ambiguous addresses, mixed-kind ranges, unbounded ranges and incomplete groups
are not guessed or partially accepted. Unlabelled or Clause-prefixed
multi-letter object syntax is not broadened.

No archived rejected model response is automatically persisted. A formerly
unparseable response becoming transport-valid does not prove its scope
interpretation correct. The scope/information safeguards remain in place.

See [the validation record](../development/context-enrichment-fixes-20260910-validation.md)
for test commands, exact baseline results and verification limits.
