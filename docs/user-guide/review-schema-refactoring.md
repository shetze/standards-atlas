# Review schema refactoring R2

R2 removes compatibility code for obsolete intermediate review/qualification formats.
It does not change prompts, acceptance predicates, qualification thresholds, Holdout
membership rules or human/publication/release authority.

## Current contracts

| Family | Only supported version | Required contents |
| --- | --- | --- |
| `partial-qualification-manifest` | 1.1 | Explicit marker; source specification and comparison policy |
| `partial-review-publication` | 1.1 | Explicit marker; confirmed review snapshot and Workbench evidence |
| `partial-qualification-campaign` | 2.0 | Explicit marker; specification, `review_evidence` and closed frozen inputs |

Markers are required at direct model, JSON/YAML, nested and file inputs. An absent marker
is not silently defaulted. Writers check the current registry before publishing output;
obsolete input is never updated in place. The two semantic suites remain schema 1.0.
Review package/state, Workbench state, archive and Handoff envelopes also remain 1.0.
The independent current-only R1 families remain 1.1.

## Evidence mode is not a format version

All three supported preparation paths produce a campaign artifact with schema 2.0:

```json
{
  "schema_version": "2.0",
  "kind": "partial-qualification-campaign",
  "review_evidence": {"kind": "archived_handoff"}
}
```

This is an excerpt, not a complete campaign plan. Atlas fills in and hashes the complete
contract; do not edit campaign JSON or maintain hashes by hand.

**`external_suites`** uses the manifest's explicit semantic suites without an Atlas review
reference. Empty suites are also structurally valid for planning but still fail semantic
release coverage. This mode makes no Atlas context/Workbench/archive assertion.

**`atlas_publication`** uses explicit suite paths whose `atlas-review:` references are bound
to matching `review-evidence.json` files. Both unchanged suites of every publication are
required. External suites may coexist but acquire no Atlas review binding. Frozen campaign
inputs contain the complete publication evidence, including its Workbench envelope.

**`archived_handoff`** uses the existing `review_bundle` pointer, resolved relative to the
manifest. It requires exactly one published review snapshot, its unchanged suite pair,
and `inputs/review-package.zip`. Recorded source, review and Workbench histories are verified
against the same publication snapshot. Missing/unexpected members, invalid hashes and
contradictory bindings are errors, not reasons to fall back to a simpler evidence mode.

The artifact declares its mode explicitly; Atlas derives it from validated inputs on
creation and checks it again against the frozen inputs on read. The input directory also
has a closed physical file inventory: merely removing a file's manifest entry cannot hide
that file. Runtime datasets, execution receipts and evaluation reports remain outside that
input directory. Local hashes establish consistency, not protection from an actor capable
of rewriting every linked artifact coherently.

## Workbench evidence remains explicit

Publication 1.1 always contains a valid `workbench` envelope. `journal_present: false`
records that a local journal was not captured. `journal_present: true` with no reveals is
a different state. Neither proves that the Holdout was never accessed elsewhere. The
human Holdout-use declaration remains mandatory for publication. A null or missing envelope
cannot stand in for an unrecorded state, even if a caller recalculates the publication hash.

Only confirmed/corrected human predicates become suite checks. Model proposals, exact
false/null/empty decisions, deferred tasks, the original source context and mandatory
coverage retain their existing semantics.

## Existing working data

- **Current 1.1 publications and current review package/state data** remain usable without
  hash changes or repeating human decisions. Current source/rule bindings must still pass.
- **An old source manifest 1.0** must be replaced by a current source manifest before
  further preparation. Update the author-maintained configuration deliberately (the shipped
  template is current), without modifying frozen evidence or claiming a new human review.
- **Old publications 1.0 or campaign artifacts 1.0/1.1/1.2** are no longer consumed. Keep
  them unchanged as historical files. Publish a new current snapshot from the original review
  package, then prepare a new campaign output. There is no publication/campaign migration.
- **A Handoff with an embedded obsolete source manifest** is rejected. Create a new Handoff
  from a current source manifest and the original review package. Current Handoffs with
  manifest/publication 1.1 already satisfy the unchanged Handoff envelope contract.

Do not patch version fields in frozen artifacts, recalculate their hashes manually, or
bind old execution results to a new campaign. The new 2.0 campaign has its own fingerprint;
old repetitions/activations cannot be resumed under that different identity. Unchanged
current 2.0 campaigns retain the usual resource checks and same-contract resume behavior.
No loader deletes rejected artifacts, resets review state or starts a model to repair them.

## Workflow

The existing commands and permissions are unchanged. For the complete review route, use
[the Handoff workflow](partial-review-handoff.md): preview and publish the confirmed suites,
archive and manifest, then prepare the qualification campaign in a new output directory.
For direct suite publication, use [the review import workflow](partial-review-packages.md).
The schema mode is selected automatically; there is no user flag to grant a higher or
lower evidence level.

`partial-review-handoff` still starts no models. Its preflight runs before campaign freeze;
qualification and activation remain separate operations with unchanged gates. R2 introduces
no MCP approval/publication capability and does not modify the Web decision interface.
Other schema-family cleanup and the global refactoring guard remain R3/R4.
