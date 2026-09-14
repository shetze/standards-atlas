# Review workbench

Review source-bound Development and Holdout packages in a local, paginated HTML interface.
This is the human stage after [package construction](partial-review-packages.md) and optional
[Codex/MCP preparation](partial-review-preparation.md). No LLM runs in this service. The
interface does not build selections, publish reference suites or activate qualification rules.

## Start the service

Use the directory **containing** the review-package directories, not a package file, corpus
workspace or qualification archive. For example:

```text
local/review/partial-semantic/
  taxonomy-v1/
    review-package.json
    review-state.json
  taxonomy-selected-v1/
    review-package.json
    review-state.json
    review-queue.json
```

```bash
uv run --extra chat standards-atlas chat serve \
  --service review-workbench \
  --review-workspace local/review/partial-semantic \
  --host 127.0.0.1 \
  --port 8090
```

Open `http://127.0.0.1:8090` in a local browser. Port 8090 is an example that can coexist with
RamaLama on 8080, a prompt workbench on 8089 and MCP on 8765. The shared `chat serve` default
remains 8765; pass a free port explicitly when services run together. Stop with Ctrl+C.

The `chat` extra supplies Starlette and Uvicorn, as for the existing prompt workbench. Review
startup does **not** need `cfg/llm.yaml`, a manifest directory or a running RamaLama server.
`--service-type review-workbench` is an alias. Existing prompt-workbench behavior is retained;
its LLM/manifest paths are validated only when that service is selected.

The registry must already exist. Only immediate subdirectories with safe alphanumeric,
hyphen or underscore handles are exposed. Symlink paths and unavailable/invalid packages
are refused. Full source artifacts larger than the local application limit are refused,
not silently shortened. No web request accepts arbitrary filesystem paths.

## Work through a package

Enter a stable **Reviewer** identifier and select the intended package. The identifier is
self-declared provenance, not an authenticated identity. The last case visited is saved on
the server separately for each reviewer and package. Browser storage only remembers the
reviewer identifier and package handle; it does not contain clause text, draft decisions,
model recommendations or source hashes.

The queue uses the fixed `review-queue.json` order materialized in Slice 2. Without that bound
queue, the package's own case order is used. The UI does not silently rerank cases as reviews
are completed. It supports pages of 5, 10, 20 or 50 cases and filters for split, document,
full-text/identifier search, unresolved attributes, completeness, deferred decisions and
cross-attribute conflicts. Filtering never changes Development or Holdout membership.

The case display separates three kinds of information:

- **Source:** the complete frozen clause text, source identifiers and structural context.
  Ancestor headings, the local heading and other available facts are shown ahead of absent
  structural fields. Original fact indices are retained for evidence binding. Structural
  origin/authority remains explicit; extracted or unattributed context is not promoted to
  a confirmed structural fact.
- **Preparation:** selectable proposal revisions with their exact predicates, reasons,
  producer/model, provenance and evidence quotations. These are not human labels.
- **Decision:** an explicit action per attribute, the current human decision and an append-only
  human revision history. Confirmed fields are left unchanged unless deliberately superseded.

Evidence highlighting uses fixed colors **and text labels** for support, counterevidence and
context. Overlapping quotations retain all labels. The browser renders literal text nodes
and validated source segments, not HTML or Markdown supplied by Codex. Unicode positions are
resolved in Atlas; the browser never recalculates Python character offsets using JavaScript
UTF-16 offsets. Selecting another proposal updates the highlighting and clears any staged
confirmation for that attribute, so the intended reviewed revision cannot silently change.

## Make explicit decisions

| Action | Persisted meaning |
| --- | --- |
| Leave unchanged / not reviewed | No event and no inferred value. |
| Confirm selected proposal | Accept exactly that visible stored proposal revision. |
| Set and confirm own value | Record an explicit typed predicate, with a required explanation. |
| Defer | No predicate; the attribute remains unresolved. |
| Reject proposal | Reject that proposal without creating a replacement or negative value. |

Scalar editors distinguish a missing choice from explicit `false` and `null`. Collection
editors distinguish **exactly these values**, **at least these values**, and **must be empty**.
An exact empty collection needs an explicit empty-list confirmation in the editor. Open
role-relation objects are entered as rows with `actor`, `relation_class` and `target`, never
as handwritten YAML or JSON. Changing a prior human decision requires a comment.

“Offene sichtbare Vorschläge vormerken” stages only displayed proposals for attributes without
an accepted current decision. It does not save anything, does not affect other pages and does
not expose hidden Holdout proposals. Every save requires the human-review checkbox. Only the
explicitly selected actions are submitted; untouched fields stay untouched.

One save is one atomic batch. A later invalid field, duplicate attribute, stale revision or
mismatched view rejects the entire batch before its state write. The server binds the batch
to the displayed package, source, rules, reviewer, state revision and visible proposal hashes.
A later MCP proposal cannot silently replace the proposal being confirmed. Concurrent CLI,
MCP or web writes require reloading and reviewing the new state; errors retain browser inputs.
There is no automatic retry that turns an old approval into a fresh one.

`Ctrl/Command + Enter` saves; `Alt + Left/Right` navigates cases. “Speichern & weiter” saves and
opens the next case in the current filtered sequence. Navigation warns about unsaved decisions
or initial-assessment text. A note that has not been explicitly recorded is not a saved review;
there is no draft autosave that could be mistaken for approval.

## Holdout: source first, assistance second

Holdout membership remains frozen. On first inspection, the server withholds model proposals,
their evidence segments and candidate ranking rationales. This is response filtering, not
merely hidden HTML. The human can enter decisions without seeing recommendations.

To request assistance, first write a source-based initial assessment and explicitly choose
“Ersteinschätzung protokollieren & Empfehlungen einblenden”. Atlas records the assessment,
reviewer, time, source/rules binding, review revision and exact disclosed model-proposal hashes
in the local workbench journal. This records an exposure, **not a semantic decision**. Historical
candidate/reference proposals remain withheld even after model assistance is revealed. Newer
model proposals require another explicit reveal and are not automatically added to an earlier
exposure. The reveal is remembered per reviewer, not globally for everybody using the package.

The blind gate concerns machine proposals. Existing human decisions remain visible as review
history; the UI is not a blinded multi-rater experiment or an authenticated separation between
reviewers. Someone with local filesystem, shell or other corpus access may already have seen
Holdout material. This service cannot prove otherwise. The existing import-time declaration
of Holdout use remains mandatory for publication.

## Coverage and publication

Separate Development and Holdout cards show selected cases, completely confirmed cases and
confirmed attributes. Deferred, rejected and untouched attributes never count as negatives
or as complete cases. The detailed report retains frozen coverage requirements, class/stratum
distributions and cross-attribute contradictions. “Ready” concerns the frozen review contract;
it is not a live-source check, a statistically representative sample claim or a release.

Use the existing CLI importer for source/rule/overlap verification and suite publication:

```bash
uv run standards-atlas evaluation partial-review-import \
  --package local/review/partial-semantic/taxonomy-selected-v1 \
  --dry-run
```

Publication still needs `--output`, `--publish` and a truthful `--holdout-declaration`, as
explained in [the review-package guide](partial-review-packages.md). A new model suggestion,
page visit or initial assessment does not enter the suites. There is no publish endpoint in
the workbench. Existing suite formats and qualification/activation thresholds are unchanged.
The [handoff command](partial-review-handoff.md) performs publication and campaign packaging
in one atomic operation after the explicit human review is complete.

## Persistence, security and recovery

```text
<package>/
  review-package.json          # unchanged immutable source/task/selection contract
  review-state.json            # shared proposals and explicit human decisions
  history/<state-hash>.json    # existing review-state history
  workbench/
    state.json                 # schema 1.0: bookmarks and Holdout exposure ledger
    history/<hash>.json        # earlier workbench metadata revisions
```

Workbench metadata is separately hashed and bound to the package. It does not confer
semantic authority and is not folded into the immutable package hash. Keep the **whole review
package directory**, including `workbench/`, for continued review. New publication 1.1
includes the checked Workbench journal and all recorded revisions; older publication 1.0
does not retrospectively gain this evidence. The [qualification handoff](partial-review-handoff.md)
exports the suite pair, full review ZIP and ready campaign manifest together, and keeps that
snapshot in the frozen qualification campaign and its final evidence archive. The suite YAML
alone is still not an exposure ledger; retain its bound evidence and archive.

Both metadata and human reviews use the existing package writer lock and crash-safe writes.
A stale lock must be investigated before manual recovery, as in the existing package workflow.
After a lost connection or storage error, reload and inspect the persisted revision before
retrying; do not assume a failed response means the write was not committed. A server restart
invalidates browser CSRF/view tokens, but leaves persisted decisions and navigation intact.

The service accepts only loopback bind addresses and same-origin browser requests. It checks
Host/Origin, including port, uses a per-process CSRF token and signed view receipts, rejects
oversized bodies (including streamed/chunked payloads) and sets a restrictive content
policy/no-store headers. No CORS or
external scripts are enabled. This prevents cross-origin web pages and rendered source text
from submitting reviews; it is **not authentication against another process running under
the same local account**. Never reverse-proxy it as an unauthenticated public review service.
