# From human review to a frozen qualification campaign

The complete path is: [build the source-bound package](partial-review-packages.md),
[prepare selection and recommendations through MCP](partial-review-preparation.md), make
explicit decisions in the [Review Workbench](review-workbench.md), then create the immutable
handoff described here. No hashes, source identifiers or reference-suite YAML need editing.

The handoff does **not** run models, invent missing decisions, approve taxonomy rules or
activate a candidate. Qualification and release remain separate operations with the existing
quality, freshness, completeness and cost gates.

## 1. Check the completed review

Use the **source campaign manifest**, not an already generated handoff manifest. It declares
sources, the Golden corpus, engineering sentinels, variants and qualification budgets. The
review package must retain every selected Development and Holdout task. A postponed, rejected
or untouched attribute remains unresolved even when a model has proposed a value.

```bash
uv run standards-atlas evaluation partial-review-handoff \
  --package local/review/partial-semantic/taxonomy-selected-v1 \
  --manifest cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml \
  --holdout-declaration '<actual reviewed statement about known prior Holdout use>' \
  --dry-run
```

Replace the declaration with the responsible human's actual statement. It is provenance,
not a formula proving independence. The command rechecks source text and structural context,
all bound inputs/rules, selected-task completeness, typed predicates, coverage, contradictions
and the full recorded Workbench history. It also checks the requested campaign's Golden and
sentinel populations, including draft Golden membership and equivalent source content, against
the fixed Holdout. The review profile must cover every required campaign dimension. Newly supplied semantic
suites or sentinels cannot introduce unreviewed known cases and then disappear when replaced
by the reviewed suite pair; those cases must first enter a completed review package.
A successful dry-run also
builds and verifies the full archive in memory, including the closed file inventory and size
limits; it does not skip archival checks or write an output directory.

Exit 1 means the review/declaration is incomplete; the JSON report lists blockers. Exit 2
means invalid input, changed evidence or an I/O error. Dry-run writes no publication, archive
or campaign. A successful review check is not a passed qualification.

## 2. Create the immutable handoff

```bash
uv run standards-atlas evaluation partial-review-handoff \
  --package local/review/partial-semantic/taxonomy-selected-v1 \
  --manifest cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml \
  --campaign-id taxonomy-reviewed-v1 \
  --output local/review/partial-semantic/taxonomy-handoff-v1 \
  --holdout-declaration '<actual reviewed statement about known prior Holdout use>'
```

`--campaign-id` is optional; otherwise the original campaign ID is retained. Use a new ID
or a separate qualification output directory when an earlier campaign is already frozen.
Nothing silently replaces a prepared campaign or its references.

The output directory is committed in one same-filesystem rename:

```text
 taxonomy-handoff-v1/
   campaign.yaml                # generated, ready for the qualification workflow
   source-campaign.yaml         # exact original manifest, unchanged
   review-handoff.json          # versioned file inventory and review/archive bindings
   review-package.zip           # portable frozen package, preparation and audit evidence
   review/
     development.yaml           # confirmed human predicates only; suite schema 1.0
     holdout.yaml               # confirmed human predicates only; suite schema 1.0
     review-evidence.json       # publication 1.1, including Workbench exposure history
     review-report.json         # completeness, coverage, conflicts and exposure summary
```

There is no intermediate public state containing only one suite or a suite without its
archive. Retrying an identical snapshot is idempotent. Changed decisions, proposals or
Workbench revisions require a new output directory; existing handoffs are never overwritten.
The original manifest and live review state are not changed by the handoff.

Atlas generates the suite pair and replaces the source manifest's `semantic_suites` list with
one `review_bundle: .` pointer in manifest schema 1.1. The comparison, source selection, quality
thresholds, repetition count, models and profiles stay unchanged; only the optional campaign
ID may differ. Thus inherited historical suites are replaced by the complete reviewed pair,
not accidentally counted again alongside their reviewed successors.

The new pointer is relative to **the generated manifest's directory**. Other source/matrix/
profile paths are automatically expanded using the original project working directory.
Copying the whole handoff therefore preserves its hashes and does not require editing its
suite paths. Original source and configuration files must still be available for a live
preparation or resume check.

## 3. Use the existing qualification workflow

```bash
uv run standards-atlas workflow plan \
  --task qualification \
  --manifests local/review/partial-semantic/taxonomy-handoff-v1/campaign.yaml

uv run standards-atlas workflow run \
  --task qualification \
  --manifests local/review/partial-semantic/taxonomy-handoff-v1/campaign.yaml
```

For a handoff manifest the plan starts with `partial-review-check-handoff`, followed by
`partial-qualification-prepare`, `partial-qualification-run` and
`partial-qualification-evaluate`. The preflight always runs, including workflow resumes;
it is not skipped because an old review marker exists. The preflight validates evidence
already confirmed by humans; it is not another human decision or an automatic publication.

The same boundary is enforced when calling preparation directly:

```bash
uv run standards-atlas evaluation partial-qualification-prepare \
  --manifest local/review/partial-semantic/taxonomy-handoff-v1/campaign.yaml \
  --output local/evaluation/taxonomy-reviewed-v1/campaign
```

All campaign artifacts use schema **2.0**. Handoff campaigns declare
`review_evidence.kind: archived_handoff` and pin
`inputs/semantic-review-bindings.json` plus `inputs/review-package.zip`. Original text,
source context, human decisions, exact proposal revisions and the recorded Holdout exposure
history therefore survive deletion or movement of the live review workspace. Model datasets
contain source inputs only; reference labels, recommendations and reviewer assessments do
not enter requests through this handoff.

A direct run/evaluation of the frozen campaign checks its copied evidence, not mutable
external review files. Matching installed qualification resources are still required.
Preparation's `--reuse-frozen`, used by the workflow, additionally rechecks the live sources/configuration;
changing those inputs does not mutate the previous campaign.

The existing qualification archive now retains the nested review ZIP rather than omitting
it as a generic ZIP member. Its ordinary envelope checksums bind that ZIP along with the
campaign and evaluation evidence. Incomplete/rejected qualifications can still be archived;
review completeness never substitutes for fresh quality evidence or a separate activation.
See [final qualification and controlled activation](taxonomy-partial-qualification.md).

## 4. Archive an unfinished review independently

A review need not be complete to preserve its current evidence:

```bash
uv run standards-atlas evaluation partial-review-archive \
  --package local/review/partial-semantic/taxonomy-selected-v1 \
  --output local/review/archives/taxonomy-review-checkpoint-01.zip

uv run standards-atlas evaluation partial-review-verify-archive \
  --archive local/review/archives/taxonomy-review-checkpoint-01.zip
```

The first command acquires the same lock used for human decisions and Workbench reveals.
It snapshots the complete package and current review state, available prior state snapshots,
preparation indexes/selections and lineage, the fixed queue, the Workbench journal/history
and exact bytes of all package-bound inputs. It rejects changed bound inputs, symlinks,
other active-writer files and unexpected files instead of silently exporting unrelated
workspace content. The original corpus/run archive itself is not duplicated: complete frozen
clause text, source structure and rules are already inside the review package. Historical
selection signals and their original artifact identifiers are retained in preparation indexes;
large historic run archives and unbound raw reports are not copied into the checkpoint.

The ZIP has fixed member metadata and sorted entries. Its versioned manifest inventories
member sizes/hashes, package/state identities and input-to-member bindings. It contains no
live lock files. The writer stages the ZIP and commits atomically; changed content cannot
overwrite an existing checkpoint. Keep writable packages for continued work; this command
exports audit evidence, not a new editable review session or a suite import.

Verification is offline and performs **no extraction**. It replays package/source, decision,
queue, parent-lineage and Workbench invariants in addition to transport checksums. It needs
neither the original run/dataset nor the previous review workspace. A valid checkpoint may
still contain unresolved tasks; `frozen_evidence_verified` is distinct from
`live_sources_verified` and from publication readiness.

Limits are 64 MiB per ZIP member, 512 MiB compressed/expanded archive content, and 20,000
members. Duplicate names, path traversal, encrypted members, symlinks and unsupported
compression methods are rejected. These limits fail explicitly, without truncating text or
omitting decisions. Review packages include source text and reviewer details; treat the
resulting archives with the same access restrictions as the source corpus.

## 5. Holdout disclosure, lineage and current contracts

Publication schema **1.1** contains a checked Workbench snapshot with all recorded revisions.
The summary distinguishes `recorded` from `not-recorded`. The Workbench evidence envelope
is mandatory; obsolete publication 1.0 and absent/null evidence are rejected. An explicit
`journal_present: false` remains valid but does not prove the absence of earlier exposure.
Neither recorded nor unrecorded histories prove the absence of earlier external access.
The explicit human Holdout-use declaration remains mandatory for publication.

Materializing a further Development selection retains every existing Holdout member, human
decision and exposure event. Workbench state/history are rebound automatically to the new
package identity; the parent package/state and any parent Workbench evidence remain recorded
in selection lineage. This closes the gap where changing the review package could otherwise
make already revealed Holdout suggestions appear unexposed.

Review package/state, Workbench state and semantic-suite schemas remain **1.0**. The archive,
Workbench-evidence and handoff envelopes start at **1.0**. Manifest schema **1.1** and campaign
artifact schema **2.0** are separate, current-only version families. Obsolete manifest 1.0,
publication 1.0 and campaign artifacts 1.0/1.1/1.2 are rejected. The explicit `semantic_suites`
path remains current as `external_suites` or `atlas_publication`; it does not gain an archive
claim merely by being loaded. See [R2 regeneration boundaries](review-schema-refactoring.md).
The independent `partial-review-import` command also now captures Workbench evidence when
exporting new publications, without requiring a campaign handoff.

No MCP tool can confirm human decisions. Neither MCP nor the Web UI can publish suites,
create handoffs or activate candidates. The Web UI retains its explicit human-confirmation
boundary; publication and delivery remain separate local CLI operations. Reviewer names
and local hashes provide traceability, not authenticated human identity, proof of model
training isolation or protection against a privileged actor rewriting all local evidence.
