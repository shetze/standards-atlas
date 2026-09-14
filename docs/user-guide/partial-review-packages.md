# Source-bound semantic review packages (Slice 1)

A review package prepares human reference decisions **before** freezing a partial
qualification campaign. It is not a model run, a Golden publication, a taxonomy-rule
approval or a release activation. The human CLI and optional MCP preparation adapter share
the application contract in `semantic_qualification/review_package`. This guide describes
the Slice-1 foundation: package construction, human decisions and validated suite import.
[Candidate indexing and MCP preparation](partial-review-preparation.md) are available in
Slice 2; the [HTML Workbench](review-workbench.md) and
[archived qualification handoff](partial-review-handoff.md) complete the workflow.

## Build from the existing corpus

Use the same project-relative campaign manifest as the qualification workflow. It points
to exactly one existing run/archive or source dataset and to the actual Golden and
sentinel inputs. The build starts no model and does not modify those inputs.

```bash
uv run standards-atlas evaluation partial-review-build \
  --manifest cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml \
  --output local/review/partial-semantic/taxonomy-v1 \
  --holdout-size 20
```

The known Development set is the union of the manifest's Development semantic suites,
its engineering sentinels, additional `--development-suite` inputs and explicitly supplied
`--development-id` values (repeatable). No known case is dropped. Previously discussed
cases that are not in these inputs must be supplied explicitly; Slice 1 does not infer
membership from old conversations or unstructured run reports. Synthetic taxonomy-readiness
fixtures are not silently substituted for real corpus clauses.

Existing Holdout suite membership is retained. Additional Holdout cases are selected by
seeded, proportional document/clause-type sampling from the eligible remainder, without
examining expected labels or candidate answers. Every known Golden case present in the
population, including draft cases, and the entire Development/Sentinel set is excluded.
Duplicate example, document/clause and document/reference coordinates fail the build.
Content-equivalent clauses (Unicode NFKC, whitespace and case) are excluded across splits;
only one representative of each content group can enter Holdout. Normalization for this
check never changes the text or its actual source hash. Insufficient eligible sources is
an error, not a reason to weaken exclusion rules.

`--seed` overrides the manifest seed. `--id` and `--version` identify the package and its
future suites. `--profile` accepts a predeclared review profile; otherwise required
attributes come from the campaign. A supplied profile cannot omit campaign requirements
or attributes of an existing semantic suite. `--instructions` freezes additional project
annotation guidance as text. No annotation YAML or manually calculated hash is needed.

## What is frozen

`review-package.json` contains the source-only population and the exact selected tasks,
Development/exclusion memberships, seed, profile, annotation rules and their fingerprints.
Each source contains the complete unchanged corpus text, example ID, document key, clause
ID, full clause reference, text hash and the source-structure projection, including known
ancestor headings and provenance. Text and context have **separate** hashes. Source values
without established authority remain unattributed; generated semantic context is not
promoted to source structure. Explicitly marked truncated inputs are rejected. An upstream
extractor's silent omission cannot be detected merely by hashing its output; defer when
necessary source context is missing.

Task schema, task definition, semantic-profile reference and versioned review guidelines
are copied into the package. Changing external Golden/sentinel/reference files, custom
instructions or the bound rule resources blocks the subsequent import. The original
campaign manifest path/hash is recorded as build provenance, but it is not a live lock:
adding the generated suites to that manifest is the intended next step. The frozen package
continues to define membership and rules regardless of later manifest edits.

`review-state.json` stores proposals and human decisions in separate, append-only revision
sequences. Every change checks the expected current revision. The previous state is retained
under `history/` before atomic replacement. Rebuilding an existing package is refused,
even if it appears to contain only an initial review. No `--force` silently resets work.

An old published suite is retained as a historical proposal with its original reviewer,
version/status and review reference, not as a newly performed review. In particular,
legacy suites do not prove a context/rules binding. In this slice they need explicit
confirmation or correction. Engineering sentinels remain engineering suggestions.

## Inspect and decide without editing generated data

```bash
uv run standards-atlas evaluation partial-review-show \
  --package local/review/partial-semantic/taxonomy-v1
```

The result lists selected cases, per-split coverage, unresolved attributes and current
revision. Inspect one of the returned identifiers:

```bash
uv run standards-atlas evaluation partial-review-show \
  --package local/review/partial-semantic/taxonomy-v1 \
  --case '<example_id from the package>'
```

The full source and structure, proposal revisions and active human decisions are separate.
To confirm a particular displayed proposal, use its `proposal_sha256` and the latest
`revision` returned by the server/CLI:

```bash
uv run standards-atlas evaluation partial-review-decide \
  --package local/review/partial-semantic/taxonomy-v1 \
  --case '<example_id>' --attribute primary_function \
  --status confirmed --proposal '<proposal_sha256>' \
  --reviewer '<human reviewer>' --revision <current_revision>
```

For a manually determined value, use `corrected` with a short explanation. This status
also covers an original human decision where there was no prior proposal:

```bash
uv run standards-atlas evaluation partial-review-decide \
  --package local/review/partial-semantic/taxonomy-v1 \
  --case '<example_id>' --attribute role_semantics_present \
  --status corrected --equals false \
  --comment 'No supported role/action semantics in the complete clause.' \
  --reviewer '<human reviewer>' --revision <current_revision>
```

`--equals` accepts a JSON value: `false`, `null`, `'"requirement"'`, or `'["activity"]'`.
An exact empty set is `--equals '[]'` or `--must-be-empty`; a minimum set is repeatable
`--must-include activity --must-include output`. These operators are intentionally different:
a minimum set does not reject additional labels. The task schema validates enums, scalar
types, duplicate list members and complete role-relation tuples. False is never zero.

`--status rejected --proposal '<proposal_sha256>'` rejects the recommendation without
inventing an opposite value. `--status deferred` leaves the attribute unresolved. Neither
status carries a predicate. Changing an earlier decision requires a comment and retains
the previous decision in history. A new model proposal never replaces an accepted human
value. Confirmation always binds to the specified proposal revision, not to whichever
proposal happened to be added most recently.

The application already supports source-bound evidence quotes used by the MCP preparation adapter:
exact quotation, optional prefix/suffix, support/counterevidence/context purpose and a
`text` or `fact:<index>` target. Atlas resolves unique Unicode-code-point offsets and
rejects missing or ambiguous quotations. There is no agent-provided HTML and no HTML
rendering in this slice. A negative decision need not invent a positive-looking evidence
span where none exists.

## Validate and import both suites

Run the import preflight at any time:

```bash
uv run standards-atlas evaluation partial-review-import \
  --package local/review/partial-semantic/taxonomy-v1 \
  --publish --dry-run
```

It reopens the source run/dataset and compares full source population, identities, text
and source context with the snapshot. `--run` or `--dataset` can specify a relocated but
source-equivalent corpus. Other bound inputs must remain accessible at their recorded
locations. Preflight writes nothing; exit 1 reports unmet review/publication requirements,
exit 2 reports invalid input/integrity or I/O errors.

Default import creates **draft** suites. It can contain partial decisions when each split
has at least one confirmed attribute; omitted checks are listed as unresolved in the
report, never interpreted as negative. Cross-attribute contradictions block even drafts.
Draft status cannot satisfy existing published-reference qualification gates.

Publication requires every selected task decided, the profile's minimum complete cases
and coverage rules satisfied, no contradictory decisions, and an explicit human declaration
about the known Holdout-use history:

```bash
uv run standards-atlas evaluation partial-review-import \
  --package local/review/partial-semantic/taxonomy-v1 \
  --output local/review/partial-semantic/taxonomy-v1-published \
  --publish \
  --holdout-declaration '<reviewed statement about prior use and independence>'
```

The declaration is an actual provenance statement by the responsible person, not a magic
phrase proving independence. Check unrecorded development use, near-duplicates and
translations; the exact-content check cannot settle them. Reviewer names, timestamps and
hashes provide traceability, not cryptographic proof of human identity or a security boundary
against an actor able to rewrite the local filesystem. MCP preparation tools must not expose
`record_decision` or the publication operation as model self-approval capabilities.

The new output directory contains:

```text
development.yaml
holdout.yaml
review-evidence.json
review-report.json
```

Both suite files use the existing `partial-semantic-reference` schema 1.0. Only current
explicitly `confirmed`/`corrected` human attributes are included. `review-evidence.json`
preserves source/context/rules bindings, complete review history, the source-bound Workbench exposure journal/history and the
recomputable coverage report. New publications use schema 1.1; schema 1.0 remains readable. All four files are committed together using one same-filesystem directory
rename on the supported local POSIX filesystem. Exact repeated imports are idempotent;
changed content never overwrites an existing publication. Corrections are exported into
a new output directory. Review state history remains intact.

## Coverage policy and qualification hand-off

The default requires at least one complete case in each split and all selected attributes
on every selected case. This is a technical completeness floor, **not a claim of statistically
sufficient or balanced semantic coverage**. Per-split predicate and source-stratum counts
are always reported. A review profile can additionally require specific predicates,
documents and clause types, for example both true and false Role Presence references.
See `cfg/evaluation/partial-cascade/review-profile-v1.yaml`. Declare requirements before
review; an inclusive Process sentinel is not counted as proof of an exact set or negative.

Use [the atomic handoff](partial-review-handoff.md) to generate both suites, the review
archive and the ready campaign manifest without editing paths. The existing manual route
(adding generated suite paths to `semantic_suites`) is still supported. No new qualification engine or automatic activation is
introduced. The original manifest schema 1.0 remains readable. Handoff manifests use 1.1 and their
campaign artifacts use 1.2, retaining the review ZIP as well as semantic review bindings.
The earlier explicit-suite route still produces bound artifact 1.1 or legacy artifact 1.0;
these remain readable. Source context, suite pair and bound rules are checked at preparation,
resume and frozen-campaign load. Frozen execution does not depend on mutable external review
working files. Historical unbound suites remain supported but do not gain this new assurance.

Locks are fail-closed. After an actual process crash, inspect the owning process and artifacts
before removing `.review.lock` or a sibling `.<output-name>.review-write.lock`. Do not remove
a lock held by an active writer. Canonical/public data paths are not valid output targets.


## Browser-based human review

The [Review workbench](review-workbench.md) uses this same source/decision contract with typed
editors, atomic per-case batches, revision-bound confirmations and a source-first Holdout view.
The existing CLI commands and import rules remain supported; no manual schema conversion is
needed to open a package built before the Web UI was introduced.
