# Candidate indexing and MCP review preparation (Slice 2)

This workflow connects the [source-bound review package](partial-review-packages.md) to a
local Codex client. Atlas supplies a deterministic candidate index, full frozen sources,
annotation rules and bounded submission tools. Codex proposes an informed Development
selection, review priorities and source-bound annotation recommendations. It does **not**
make human decisions, approve taxonomy rules, publish reference suites or activate releases.
The paginated HTML workbench is Slice 3; this slice supplies its queue and evidence data.

## 1. Build and index a package locally

First build a package using the existing Slice-1 command. The registry below expects package
directories immediately below `local/review/partial-semantic/`:

```bash
uv run standards-atlas evaluation partial-review-build \
  --manifest cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml \
  --output local/review/partial-semantic/taxonomy-v1 \
  --holdout-size 20

uv run standards-atlas evaluation partial-review-index \
  --package local/review/partial-semantic/taxonomy-v1 \
  --additional-development-budget 12
```

The index automatically reads the Golden and semantic reference inputs already bound into
the package, including additional Development suites supplied at build time. It does not
rediscover them through an edited live campaign manifest. Add completed qualification
reports using repeated `--history PATH`; add known external reference files using repeated
`--reference PATH`. Supply the real local paths, not the example placeholder below:

```bash
uv run standards-atlas evaluation partial-review-index \
  --package local/review/partial-semantic/taxonomy-v1 \
  --history /path/to/completed-qualification-run.zip \
  --history /path/to/another-completed-run-directory \
  --additional-development-budget 12
```

Indexing starts no model and does not modify corpus, package membership, review decisions or
reference suites. The result returns `index_sha256`, membership counts, input artifact count,
diagnostics and the frozen additional-Development budget. Identical inputs and review state
produce the same index. Keep historical inputs as immutable snapshots.

Supported inputs are Applicability Golden schema 3.0, semantic reference suites,
`mixed-consensus-report.json`, mixed stage/before-focus reports, consensus report schema
4.0/5.0, and `partial-observation.json`. Individual JSON/YAML reports, completed directories
and ZIP archives are supported. Only recognized per-clause reports are read from archives;
raw request/response files are not executed or converted into invented observations.
Archive checksums are checked when supplied by the existing archive contract. Identical
report bytes are deduplicated. A report over 64 MiB, an active-writer archive, an unsupported
format, or a checksum mismatch fails preparation rather than producing a misleading index.

An aggregate-only `qualification-evaluation.json` is **not sufficient**: it cannot say which
bound clause and attribute produced a failure. Use the corresponding completed run archive,
run directory, or individual clause-level reports; the archive need not be uploaded to ChatGPT.

### Interpretation of historical results

Historical conclusions are selection hints, not new human confirmations or independently
re-executed evidence. Binding checks document/clause identity and original text or text hash;
incompatible/out-of-population observations remain visible as diagnostics instead of labels.
A historical context which is not independently established remains `text-only` even when
the current frozen review source has fully bound structural context. Artifact hashes prove
which input bytes were used, not that historical conclusions are true.

Published Golden/reference decisions are attribute-specific. Published Applicability does
not turn the clause into a confirmed Process-Function reference. Existing genuine decisions
in the review package remain separate and are carried forward unchanged.

Technical failures have their own count; they are neither negative labels nor semantic
conflicts. Missing, ineligible and not-evaluated observations do not manufacture default
`false`, `null` or empty selections. Current-contract historical reports retain actual explicitly reported votes;
zero-vote insufficient-evidence defaults do not raise semantic disagreement priority.

### Reproducible priority, not a confidence estimate

The transparent `review-priority-v1` ranking gives semantic/reference conflicts priority 90,
reported value disagreement 80, observed unresolved semantics 60 and reference-coverage gaps
25. Rare document/structure strata add 10, unattributed legacy context adds 5, capped at 100.
These are review-order heuristics, **not probabilities, safety claims or acceptance thresholds**.
Cases are ordered by decreasing priority and then stable example ID. Technical failures alone
do not raise semantic priority. Reasons and relevant attributes accompany each candidate.

Codex should balance difficult boundaries, missing attribute coverage and document/structure
diversity, while retaining some clear positive/negative controls. Atlas does not equate
"top N by score" with a statistically representative sample or complete semantic coverage.

Local inspection is available without MCP; use the returned index identifier unchanged:

```bash
uv run standards-atlas evaluation partial-review-candidates \
  --package local/review/partial-semantic/taxonomy-v1 \
  --index '<index_sha256>' --limit 20 --offset 0
```

Filters: `--membership development|candidate`, `--document-key`, `--clause-type`, `--reason`
and `--query` (all query terms in text/reference). Results include `next_offset`. Holdout and
content-equivalent proxies are not part of this Development candidate API.

## 2. Enable the optional MCP interface

Merge these fields into the existing `mcp:` mapping in `cfg/mcp.yaml`; do not replace your
transport, bearer-token, host, origin, exposure or audit settings:

```yaml
mcp:
  review:
    enabled: true
    workspace: local/review/partial-semantic
    allow_holdout_assistance: false
  capabilities:
    review_preparation: true
```

Both settings are **false by default**. `review.enabled` enables five reads;
`capabilities.review_preparation` additionally enables two model-only submission tools.
Disabling `expose.clause_text` also disables effective review access. Document allowlists
apply to the entire population: a package containing a disallowed document is refused,
not partially exposed. Keep this trusted workspace local and non-symlinked. The client
addresses immediate child directories by opaque handles, never arbitrary filesystem paths.

Restart an already running server after changing configuration:

```bash
uv run standards-atlas mcp restart --config cfg/mcp.yaml
```

For a dedicated review client, generate the configuration fragment with the new flag:

```bash
uv run standards-atlas mcp codex-config \
  --url http://127.0.0.1:8765/mcp/ \
  --name standards-atlas-review \
  --review-preparation
```

Apply the generated fragment to the Codex configuration used for this review session. The
flag selects only the seven review tools plus `get_server_info`; it deliberately **omits**
generic corpus readers which would bypass the review-specific Holdout disclosure policy.
Without the flag the previous tool allowlist is unchanged. The separately printed endpoint
registration command does not install the fragment's tool allowlist by itself. Do not keep
an unrestricted parallel Atlas connection enabled in a supposedly isolated review session.
The official [Codex configuration reference](https://developers.openai.com/codex/config-reference)
documents `enabled_tools`; server-side checks remain the decisive authorization boundary.

The tools are:

| Tool | Purpose |
| --- | --- |
| `list_review_packages` | Discover trusted package handles and revisions. |
| `get_review_package` | Read frozen rules, task schema, capabilities and candidate index IDs. |
| `list_review_candidates` | Page/filter bound Development candidates and historical hints. |
| `get_review_case` | Read complete frozen original text/context and separate proposals/reviews. |
| `list_review_cases` | Page materialized cases in the fixed review queue. |
| `submit_review_selection` | Store a bounded selection/prioritization proposal, not approvals. |
| `submit_review_annotations` | Atomically store source-bound model recommendations and evidence. |

`get_review_case` returns complete text or refuses when `max_clause_characters` is too small;
it never silently truncates review sources. Increase the local exposure limit when needed.
Page sizes, batch counts and serialized submission sizes are bounded for both service use
and transport. Tool annotations are descriptive; enforcement is in the application/service.

## 3. Let Codex propose the selection

The client reads package rules, effective limits and a selected non-stale index with its
frozen budget, uses candidate filters to
identify useful cases and retrieves full sources for those it examines. It submits a
`SelectionRequest` with declared actor/model, overall rationale, additional Development IDs
and source-bound priorities/rationales. Every addition requires its own priority and rationale.
It copies source/package/index tokens returned by Atlas; it does not calculate or edit hashes.

Known Development cases cannot be removed. Additions must be eligible, outside the Holdout
and within the frozen budget. Repeating known selections, source/content duplicates or an
attempt to add Holdout cases fails validation. The proposed total order retains **all** known
cases, including unchanged Holdout membership. With assistance disabled, the client cannot
supply Holdout priorities. The receipt is explicitly `proposed-not-materialized`.

The technical owner then materializes the stored proposal with the local operation:

```bash
uv run standards-atlas evaluation partial-review-apply-selection \
  --package local/review/partial-semantic/taxonomy-v1 \
  --selection '<selection_sha256>' \
  --output local/review/partial-semantic/taxonomy-v1-selected \
  --id taxonomy-v1-selected
```

This is a packaging step, **not annotation approval**. It creates a new immutable package;
it never edits the original or resamples Holdout. Existing review/proposal history is retained
and rebound to the new package. The selection, index, parent state, lineage and review queue
are copied and hash-bound automatically. An unchanged repeat is idempotent. Existing output
with different content is not overwritten. A source/rules/state change requires a new index
and selection rather than quietly applying an obsolete proposal.

The new directory is automatically discoverable in the registry. Use its handle and package
revision for the next phase. An index is optional for annotation of already materialized cases.

## 4. Return recommendations and exact evidence

For each selected case, Codex sends attribute, typed predicate, rationale and evidence quotes.
The MCP schema exposes the accepted structure directly; no manually edited annotation file
is required. An `AnnotationBatch` has a request ID and declared actor/model; its recommendations
bind to server-issued source identifiers. The call additionally binds package hash and the
expected current review revision.

Evidence uses `quote`, optional `prefix`/`suffix`, purpose `support`, `counterevidence` or
`context`, and target `text` or `fact:<index>`. Atlas resolves unique Unicode-code-point spans
against the frozen text or source-structure fact. Missing or ambiguous quotes fail the entire
batch. Codex supplies **no HTML, colors or manually computed offsets**. Slice 3 can render
these spans safely using fixed presentation rules. A well-reasoned negative annotation may
have no span; do not invent a quotation which supposedly proves absence.

Submission always creates `producer_kind=model`. There are no reviewer, confirmation,
publication or activation fields, and unknown fields are rejected. False, null and empty
values are preserved when explicitly proposed; they remain proposals until a human decides.
One invalid recommendation means no part of the batch is committed. Retry an uncertain
network result with the **same request ID, package, expected revision and payload**; it returns
the same proposal identities and the current state without duplicating proposals. Reusing the ID with changed content fails.
For a new batch, reload the current revision. New proposals never replace human decisions.

Example task for a dedicated Codex review session:

```text
Prepare the Development review for package taxonomy-v1. Read its frozen annotation
rules and use the current candidate index. Keep every known Development case and
respect the additional-case budget. Compare historical disagreements with published
reference hints, cover different clause structures and include clear controls.
Inspect full original sources before proposing annotation evidence. Submit a
source-bound selection with explicit rationales; do not alter Holdout membership.
After the selected package is materialized locally, submit model recommendations
with exact evidence quotes and meaningful counterarguments. Report your actor and
actual model identity. Do not submit HTML or claim any human confirmation.
```

## Holdout and trust boundaries

Holdout selection happened independently during package build. Indexing and agent selection
never move cases into or out of it. A newly supplied Golden/Development reference which
intersects frozen Holdout requires rebuilding with correct known exclusions, not automatic
replacement. Repeated normalized content is checked; arbitrary paraphrases, translations and
unknown prior use are not automatically proved independent.

`allow_holdout_assistance: true` is an explicit local decision after membership is frozen.
It permits reads/recommendations for actual held-out cases, but historical proposals, candidate
results and existing human answers remain withheld from those reads. Content-equivalent
proxy cases remain reserved. This does not certify an uncontaminated Holdout: prior use and
other authorized access still need honest documentation. The existing HTTP request audit is
not a complete semantic per-case exposure ledger. An agent with unrestricted shell/file or
other corpus-tool access is outside this MCP-only isolation boundary.

Actor/model fields are declared provenance, not cryptographic identity verification. Human
review uses the separate local CLI or [review workbench](review-workbench.md); only its explicit decisions
can be imported by `partial-review-import`. Tool-call permission is not semantic approval.
All previous source, coverage, overlap, qualification and activation gates remain intact.

## Persistence and recovery

```text
<package>/
  review-package.json
  review-state.json
  preparation/
    indexes/<index_sha256>/index.json
    selections/<selection_sha256>/selection.json
<selected-package>/
  review-package.json
  review-state.json
  review-queue.json
  preparation-index.json
  preparation-selection.json
  preparation-parent-state.json
  preparation-lineage.json
```

Candidate/selection files have independent schema-1.0 contracts registered in the central
schema inventory. Existing review-package and suite formats are unchanged. Entries retain
stable source identities; proposed review priority never becomes a semantic reference value.
The queue is a total fixed order: a difficult-first partial review cannot silently count as
complete Holdout coverage. Continue with the existing human-review and import workflow.


## Continue in the human review workbench

After local selection materialization and model recommendation submission, open the selected
package through [Review workbench](review-workbench.md). Its page order is the bound queue,
its evidence rendering uses the stored quotations, and only explicit human saves create
review decisions. No additional model call or qualification rerun is needed for the HTML UI.


## Preserve preparation in the qualification handoff

After completing the [HTML review](review-workbench.md), use the
[archived qualification handoff](partial-review-handoff.md) to preserve the fixed queue,
selection/index lineage, human decisions and Workbench exposure records with both suites.
A further Development materialization retains the parent Workbench history and rebinds its
identities automatically; it cannot reset a previously exposed Holdout to an unexposed state.
No additional MCP approval or publication capability is introduced.

### Obsolete historical formats (R3)

Consensus history requires schema 5.0. A rejected report includes the source/member identity
and aborts index preparation before a new index is published. There is no compatibility
conversion, inferred negative, or empty "clean history" result. Existing membership and
human decisions remain unchanged. Full archives can contain other opaque artifacts, but
recognized qualification evidence is checked when consumed. See
[Remaining schema refactoring R3](remaining-schema-refactoring.md).
