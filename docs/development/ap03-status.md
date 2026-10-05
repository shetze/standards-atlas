# AP03 status — Series H / S15-S16 technically implemented; Holdout execution blocked by missing pre-Holdout evidence

## Series H — isolated Holdout and AP03 completion

Date: 2026-10-04. This delivery implements only AP03-S15 and AP03-S16 on the supplied
post-Series-G snapshot. AP04 is not started. The start snapshot does **not** contain the private
Development reports, actually annotated verifier benchmark, fresh Finalist/B0 repetition evidence or
human H3 confirmation that Series G requires. Its own Series-G handover therefore says that Holdout
must remain untouched until those prerequisites are registered and `assertion-series-g-readiness` is
blocker-free. No real Holdout/model/Codex run and no qualification decision are manufactured here.

S15 adds a versioned, isolated Holdout campaign contract. The campaign is prepared before the final
freeze from the exact Holdout Golden suite, partition/exposure plan, explicit G0-G6 gate profile and
already authorized experiment manifests. It fixes the Finalist, optional preplanned baseline cells,
repetition counts and execution order. Optimizer access, expected-content delivery to the extractor,
adaptive variant choice, post-insight gate changes and canonical adoption are fixed off by schema.
Gate values have no qualifying numeric defaults.

`assertion-series-h-preflight` is model-free. It requires a blocker-free Series-G readiness decision
and verifies the freeze hash, campaign hash, gate-profile hash, partition/exposure hash, exact Holdout
suite, exposure-clear source groups, manifest hashes, Holdout partition, execution authorization,
repetition counts and code revision. A changed campaign/gate/partition/manifest after freeze blocks
execution instead of silently creating a new test protocol.

`assertion-series-h-run` performs only the frozen execution order and delegates every cell to the
existing bounded assertion experiment runner. It does not invoke the optimization client and has no
adaptive selection path. `assertion-series-h-finalize` revalidates the same preflight, materializes
only the existing native proposals/source packages, evaluates them with the existing
`AssertionQualificationEvaluator`, preserves every planned repetition and produces the Holdout
assessment. Technical failures, missing repetitions, cached calls, low support and critical semantic
findings remain visible blockers. A failed Holdout becomes `evaluated_not_qualified`; there is no
retune/retry path against the same Holdout.

S16 adds the explicit AP03 completion states `implemented_not_evaluated`,
`blocked_by_missing_evidence`, `evaluated_not_qualified` and `qualified_for_bounded_pilot`. A passed
Holdout still cannot qualify a pilot without a separate human release decision and a non-empty bounded
scope. The resulting quality report keeps technical implementation, experimental evaluation and
bounded-pilot qualification separate. Canonical adoption remains disabled in every state.

The finalizer also emits an AP04 handover containing only bound proposal/source-package identities,
freeze/campaign/gate/partition identities, the bounded scope and open blockers. It starts no AP04
operation and grants no knowledge-adoption authority. The static handover in
`docs/development/ap03-ap04-handover.md` records the actual status of this delivery: there are no real
Holdout proposal references yet because Series G evidence is still missing.

The public synthetic Series-H end-to-end test exercises campaign build → freeze/readiness → preflight
→ existing bounded runner with a fake gateway → native source-bound proposal materialization →
existing evaluator → Holdout gate decision → explicit synthetic bounded release. It is only a software
integration proof, not semantic model-quality evidence. Existing AP01 offline and AP02 T01-T34
reference paths and MCP access guards remain separate regressions.

Implementation verification in this environment: the final focused Series-H/schema set completed as
**102 passed**; the broader assertion-qualification plus AP01 offline, AP02 reference/source-bound and
MCP security regression completed as **232 passed, 4 skipped**; the full assertion CLI plus architecture
suite completed as **148 passed**; and all assertion-qualification integration tests completed as
**3 passed**. These suites overlap and their counts must not be added as unique tests. The four MCP
skips require the optional `mcp` Python package, which is absent here. `uv run --offline ruff check .`
was attempted, but uv could not resolve `jsonschema` from its offline cache, so Ruff never started. A
full `python -m pytest -q` was also attempted and exceeded the 300-second execution limit before
completion; no full-suite success is claimed. No real model, Codex, private Holdout or human-attestation
run was executed.

### Actual evidence / release status in this delivery

- **Technically implemented:** yes for S15/S16 contracts, CLI, schemas, reports, runbook and public
  synthetic tests.
- **Experimentally evaluated:** no. The supplied snapshot has no blocker-free Series-G readiness/freeze
  evidence and no real Holdout attempts were executed here.
- **Qualified for bounded pilot:** no. There is no real Holdout assessment and no post-Holdout human
  release decision. Canonical adoption remains disabled.

### Exact continuation point

1. Apply this delta and run local `uv run ruff check .` and full `uv run pytest`.
2. Restore/register the missing Series-F Development reports, actually annotated verifier set and
   fresh Finalist/B0 repetitions; set the project-owned G4/G5 and Series-H G0-G6 gates before any
   Holdout result is visible.
3. Prepare the exact authorized Holdout experiment manifests, then create
   `assertion-series-h-campaign-prepare` from the confirmed Holdout suite and partition/exposure plan.
4. Produce a fresh Series-G freeze/readiness binding against the **post-Series-H code revision** and
   the exact campaign hash. This delivery changes qualification code, so an earlier code freeze cannot
   authorize its execution. Obtain genuine H3 confirmation; do not synthesize it.
5. Run `assertion-series-h-preflight`. Proceed only if it is blocker-free. Then run exactly one
   predeclared `assertion-series-h-run` campaign; do not inspect intermediate results to choose a new
   variant, threshold or campaign member.
6. Run `assertion-series-h-finalize`. If gates fail, preserve `evaluated_not_qualified`; any future
   optimized version needs a new freeze and a genuinely unexposed evaluation basis. If gates pass,
   record the explicit human release decision and bounded pilot scope separately.
7. AP04 may consume the generated handover only after the AP03 completion state is understood. AP03
   itself never adopts canonical knowledge.

---
# AP03 status — Series G / S13-S14 technically implemented; real evidence and freeze confirmation open

## Series G — Verifier, cascade and stability

Date: 2026-10-04. This delivery implements only AP03-S13 and AP03-S14 on the supplied
post-Series-F snapshot. Series H is not started. The supplied snapshot still contains no registered
private Development experiment reports, annotated verifier benchmark, fresh repetition results or
human H3 freeze confirmation. Consequently no real verifier-quality measurement, new model inference,
Finalist selection, Holdout execution or qualification claim is made in this environment.

S13 now distinguishes cascade routing from final technical state. Efficient outputs that pass the
first verifier are `technically_verified`. Escalation without another check is explicitly
`needs_review`; an escalation with extraction failures/violations is `failed`. A single bounded second
verification is opt-in (`assertion-cascade --verify-escalation`) and can produce
`technically_verified` only when it completely reviews the escalation candidates and detects no missing
items. There is no generate/critique/repair loop and no automatic canonical adoption.

Series G adds an annotation-bound verifier measurement contract for false acceptance, false rejection,
abstention, verification coverage and missing-item detection. Real annotated Development cases and
synthetic mutations are counted separately. Synthetic-only evidence cannot satisfy readiness. The CLI
`assertion-series-g-verifier-evaluate` consumes explicit annotated observations; it does not create or
modify Golden truth.

Post-Series-H correction (2026-10-05): the previously missing preparation path is now explicit.
`assertion-series-g-verifier-run` reuses persisted successful Development experiment candidates and
runs only the verifier with result-cache reuse disabled. It writes a hidden verifier outcome artifact
and a blind flat review CSV. `assertion-series-g-verifier-observations-build` accepts only complete
human candidate/missing-item decisions bound to that run and then creates `verifier-observations.json`.
Verifier-call errors remain in the observations and reduce coverage instead of disappearing. Golden
content is neither rewritten nor inferred from the verifier.

S14 adds fresh-repetition evidence, an explicit G4/G5 gate profile, complete pre-Holdout freeze
identity and a readiness decision. Gate thresholds and support minima have no qualifying defaults.
Missing real annotated support, incomplete fresh inference repetitions, cached repetitions beyond the
approved limit, missing freeze material or absent human confirmation remain blockers. Series G never
sets `qualification_claim_permitted=true`; qualification still requires the later isolated Holdout and
release decision. `assertion-series-g-readiness` materializes this blocker-preserving decision.

The existing bounded experiment runner remains the mechanism for approved new inference repetitions.
Repetitions must use cache bypass and every fresh run must remain bound by report hash; Series G does
not implement Best-of-N. The freeze binds code, prompt/schema, ontologies, context/source policy,
model/backend, cascade and retry/budget policy, Development Golden, partition/exposure state, evaluator
and the concrete future Holdout campaign. A functional change after freeze requires a new freeze.

Post-Series-F/G budget-guard correction (2026-10-05): executable token-bounded manifests now bind
`max_total_tokens_per_call` in addition to the campaign `max_total_tokens`. The runner reserves that
full prompt-plus-completion amount before each call instead of reserving only `request.max_tokens`.
Known provider usage replaces the reservation with actual usage; unknown usage conservatively consumes
the reservation, including persisted `outcome_unknown` attempts across Resume. Provider usage above
the reservation blocks as a budget-contract violation. Historical manifests without the new field stay
readable for audit/reporting but cannot be executed/resumed. New comparison reports expose both
observed tokens and budget-charged tokens plus the number of calls with unknown usage. This correction
is required before Series-G fresh repetitions; it does not alter historical Series-F attempts or their
measured results.

The same correction adds model-free builders for `repetitions.json`, the explicit G4/G5 gate profile
and `freeze.json`. Repetition reports are hashed and cache use is not counted as fresh evidence;
changed clause outcomes are listed as unstable. Gate numbers and H3 remain explicit human inputs. The
freeze builder derives bound identities from the selected Finalist manifest, current code revision,
partition/exposure plan and preplanned Series-H campaign, avoiding manual hash transcription.

Correction verification in this environment: the complete assertion-qualification unit area plus
assertion CLI and architecture tests completed as **318 passed**; all existing assertion-qualification
integration tests completed as **3 passed**. The focused Series-G preparation/unit tests are included
in those counts. `uv run --offline ruff check ...` was attempted but uv could not resolve `jsonschema`
from its offline cache, so Ruff did not start. No real verifier/model, Holdout or human-review decision
was executed while implementing this correction.

Implementation verification in this environment: assertion-qualification plus assertion CLI and
architecture tests completed as **304 passed** before the final documentation-only changes. The focused
S13/S14 tests completed as **12 passed** and the complete assertion-qualification unit set as
**160 passed**. A direct `ruff` invocation was attempted but Ruff is not installed in this environment;
therefore no Ruff success is claimed. No real model, Codex client, private standards-text, Holdout or
human-attestation run was executed.

### Exact continuation point

1. Apply this delta and run local `uv run ruff check .` plus full `uv run pytest`.
2. Restore/register the completed Series-F Development reports and an actually annotated verifier
   check set. Evaluate it with `assertion-series-g-verifier-evaluate`; synthetic mutations may augment
   but not replace real annotations.
3. If the bounded second-verifier factor is to be compared, run the same Development cascade once
   without and once with `--verify-escalation`; account for the extra verifier calls explicitly.
4. Prepare the approved Finalist/B0 repetition experiments with the existing bounded experiment
   runner, using new inference attempts and cache bypass. Execute all pre-authorized repetitions; do
   not choose a best run.
5. Record the pre-Holdout G4/G5 thresholds/support minima and complete freeze bindings. The project
   owner must explicitly confirm H3; do not manufacture that confirmation.
6. Run `assertion-series-g-readiness`. Only a blocker-free result permits starting Series H; it is
   still not a qualification result.
7. Do not access Holdout or begin S15/S16 until that bound pre-Holdout state exists.

---

# AP03 status — Series F / S01-S12 technically complete; private measurements open

## Series F — S11/S12 Development baseline and prompt comparison

Date: 2026-10-03. Series F implements only AP03-S11 and AP03-S12 on the supplied post-Series-E
snapshot `standards-atlas-current-202610031442.zip` (SHA-256
`2c8b0d3aa2563bcccc9252948bb630eb078ba1e6b0f67bb960e8091c9ad8a776`). Series G is not started.

The supplied snapshot does not contain the private v8 review audit, the published Development Golden
suite, the historical v8 qualification report, or registered AP03 private experiment data. The
model-free AP03 preflight therefore reports `historical_replay_ready=false` and
`b0_experiment_inputs_ready=false`. B0 is intact (`ap03-b0.json` SHA-256
`888622019e6339379a470dccdf498109b5b1be162197ffbe4324a9b9989bb92a`), and model configurations
are declared, but their runtime availability is not verified by preflight. No real B0, P1, P2, v8
replay, Codex diagnosis, standards-text inference or semantic-quality measurement was executed in
this implementation environment. No result is invented.

S11/S12 add a Development-only Series-F preparation contract and CLI command
`evaluation assertion-series-f-prepare`. It prepares a strict B0 smoke subset followed by B0 full, P1
and P2 using the existing bounded experiment manifests/runner. B0/P1/P2 are required to have one
identical non-prompt-factor fingerprint covering code revision, Development Golden identity,
ontologies, source-package bindings, task schema, model/runtime route, effective requested parameters,
repetitions and budgets. Holdout, automatic knowledge adoption and hidden factor changes are rejected.
The preparation itself performs zero model calls and records `measured_results_present=false`.

Historical v8 replay deliberately remains the existing offline `assertion-evaluate --review` path; it
uses the stored audit snapshots and unchanged evaluator rather than regenerating v8 proposals. B0/P1/P2
execution and reporting remain the existing `assertion-experiment-run|resume|report` operations. The
new runbook `docs/development/ap03-series-f-runbook.md` gives the exact sequence and keeps the B0 smoke
separate from the full B0 statistics. P1/P2 reports can bind the B0 qualification report without a
second matcher.

The Series-E handover still records the genuine text-free Codex client tool-read as a local user gate.
That gate affects optional Codex Development diagnosis; it is not silently treated as successful here.
No Codex optimization is required to run the approved B0/P1/P2 cells.

Implementation verification in this environment: the new Series-F unit tests pass, and the focused
assertion-qualification/CLI/AP03 prompt architecture regression completed as **168 passed**. A smaller
initial focused set completed as **24 passed**. `uv run --offline ruff ...` was attempted but dependency
resolution failed before Ruff started because `jsonschema` is absent from the local uv cache and network
access is disabled. No full project pytest is claimed; the user performs final local Ruff and full pytest.

### Exact continuation point

Before claiming S11/S12 experimental completion, restore/register the original v8 audit, Development
Golden suite and required private EngineeringDocuments/source packages; confirm the approved data/model
route and budget; verify runtime availability; run the offline v8 replay when the original audit is
present; prepare and execute B0 smoke → B0 full → P1 → P2 using the generated Series-F plan; then
produce the bound reports. Optional Codex diagnosis additionally requires the real S10 client probe to
be green. Do not begin Series G until the required Development measurements or their explicit blockers
are carried forward.

---

# AP03 status — Series E / S01-S10 complete

## Post-Series-E correction 5 — preserve Codex login in isolated client probe

The user's real S10 client probe reached Codex CLI `0.160.0` but failed before MCP tool discovery with
HTTP `401 Unauthorized`. A separate `codex login status` on the same machine reported
`Logged in using ChatGPT`. The mismatch identified a probe-isolation defect: the probe replaced
`CODEX_HOME` with a fresh temporary directory in order to isolate MCP configuration, which also hid
the existing file-backed ChatGPT login. No standards text was used and no MCP tool call occurred in
the failed probe.

The probe now keeps the isolated temporary `CODEX_HOME` and single-tool MCP configuration, but if the
normal Codex home contains `auth.json` it exposes that existing login through a temporary symbolic
reference instead of copying credential bytes. The temporary probe home is created below the normal
Codex home when available, avoiding the previous `/tmp` helper-path warning. Codex executes from an
empty temporary working directory rather than the Standards Atlas repository, so project-local Codex
configuration and instructions are not loaded into this recognition check. The probe still enables only
`get_server_info`, uses the read-only sandbox, requires explicit model-call opt-in and model selection,
and marks the data scope as `synthetic-text-free-server-info`.

A deterministic subprocess-contract test verifies that the probe sees the existing auth file through a
symlink, does not copy its contents into `config.toml`, does not import an unrelated user MCP server,
runs outside the project workspace and can accept a successful `ap03-development` tool result. No
Golden, evaluator, experiment, prompt, S09 scope or Series-F behavior changed. The real Codex model
probe remains to be rerun by the user after applying this correction; no authenticated Codex/model call
is claimed from this implementation environment.

## Post-Series-E correction 4 — bounded MCP clause batch lookup

A real AP03 Development MCP probe on the user's registered corpus exposed a performance defect in
S09: the default 10-second probe timed out in `list_standards`, while the identical probe with a
60-second timeout passed after 17.879 seconds. The server/profile/tool/schema checks were already
green, so this was an allowed-read execution cost problem rather than a scope or protocol failure.

The cause was `McpDevelopmentScope.allowed_clauses()`: it resolved every allowed source-clause ID by
calling `ClauseProvider.get_clause()` separately. `EngineeringDocumentClauseProvider.get_clause()`
scans the persisted EngineeringDocument corpus, producing an N-times-corpus access pattern for one
Development view. The provider now has exact bounded `get_clauses()` and `get_documents()`
contracts. Clause lookup resolves all requested IDs in one bounded repository pass over only the
configured Development document allowlist; document listing loads descriptors only for document keys
actually present in that resolved visible set. The MCP Development clause view lazily resolves the
exact allowed clause batch once and reuses only those descriptors for list, search, sample and direct
clause reads. It still does not delegate broad document/clause list, search or sample operations to
the underlying corpus provider and does not widen the server-side Development/Holdout authority.

Regression tests explicitly make per-clause `get_clause()` unavailable to the scoped Development
view and assert that repeated list/search/get/document operations use one exact batch read. A real
provider test verifies requested-order preservation, targeted loading of the allowed document and
that neither exact clause nor exact document lookup enumerates the unrelated persisted corpus.
No prompt, Golden, evaluator, review, experiment, Codex handoff or Series-F behavior changed.

Correction verification in this implementation environment: focused MCP/provider tests **7 passed,
1 skipped**; MCP/evaluation/CLI/architecture set **210 passed, 4 skipped**; all unit plus architecture
subsets completed as **2,167 passed, 4 skipped**; selected AP01/AP02/source-bound/contract
integrations **18 passed**. A broader integration/contract/property aggregate emitted 34 passing
tests but did not complete before the environment timeout and is not reported as passed.
`uv run --offline ruff check .` could not resolve `jsonschema` from the local uv cache, so Ruff was
not executed. No model, Codex client, network or private standards-text run was performed in the
implementation environment. After applying the correction, the user reran the original real-corpus
probe with the default timeout: all checks passed in **0.697 seconds real time**, compared with the
pre-correction 17.879-second run that required a 60-second timeout. The S09 real-data performance
gate is therefore locally confirmed closed.

## Post-Series-E correction 3 — English Review Workbench and explicit target fields

A Series-D HITL smoke review showed that the target heading was present but not clearly identifiable as
a separate decision-driving field: it appeared as a large title inside the target-source card without an
explicit `Target heading` label. The Workbench now renders `Target heading` and `Target body` as
separate labelled fields under the target-clause banner. The target heading remains visually dominant,
while the body and bound structural context remain distinct source surfaces.

The Review Workbench now uses English as its default UI language across the existing applicability and
assertion-review surfaces: static HTML, queue/navigation text, review actions, validation messages,
status/value formatting, typed editors and date formatting (`en-GB`). No language selector or new i18n
runtime was introduced; this is a deliberately small presentation correction and does not change any
review, package, source, Human-attestation, MCP/Codex or Golden-publication contract. Source text and
model-provided content remain byte/content data and are not translated.

## Post-Series-E correction 2 — S07/S08 hash diagnostics and HITL visual hierarchy

The Series-D smoke test after the first post-Series-E correction exposed two usability/verification
issues. Both are corrected without changing the finished S08 package contract or the Series-E MCP/Codex
authorization surface.

- `ReferenceCorpusPlan` now verifies `plan_sha256` against the serialized JSON-shaped payload before
  Pydantic normalization. A stale or modified plan remains rejected, but the error reports the stored
  and expected digests and instructs the operator to regenerate `partition-and-exposure.json` from the
  original S07 request. Fresh plans generated by `assertion-reference-corpus-plan` round-trip unchanged.
- The assertion HITL view now gives decision-driving information primary visual weight: the
  Development/Holdout badge is larger, the source-first instruction is a dedicated callout, and the
  target clause is rendered as a prominent target block with its own Heading (or explicit absence)
  and body. Supporting structural context remains visible below it instead of competing at the same
  visual level.

This correction performs no model call, changes no Golden content, and does not weaken plan-integrity
checks. A hash mismatch means the stored plan content and its stored digest differ; regeneration, not
manual hash repair, is the recovery path.

Validation in the implementation environment: **360 passed, 4 skipped** across assertion
qualification, MCP, web, assertion CLI and architecture tests; `node --check` passed for the changed
Workbench JavaScript. `uv run --offline ruff check .` could not resolve `jsonschema` from the local
cache and therefore produced no Ruff result.

Date: 2026-10-03. Series E implements only AP03-S09 and AP03-S10 on the supplied,
locally verified post-Series-D snapshot `standards-atlas-current-202610030602.zip`
(SHA-256 `3860ea7cf07d519c2914c7ef55a97f3ce381457841dda86fd1234010a6d0c5dd`).
Series F is not started.

No real standards-text optimization, remote LLM inference, private corpus run or semantic-quality
experiment was executed in Series E. The local environment has no `codex` executable. The genuine
Codex-client MCP tool-read probe is therefore implemented but recorded as **not executed**. All new
access-control, handoff and staging tests use synthetic data only.

## Post-Series-E correction — S07/S08 preparation binding

A locally observed Series-D usability/integration gap was corrected on the post-Series-E snapshot
without starting Series F. `evaluation assertion-review-workbench-build` no longer asks an operator to
copy `corpus_plan_sha256`, `partition`, `source_group`, source-package paths, or ontology class/property
lists into a second manifest. Its build manifest now binds the actual S07
`partition-and-exposure.json`; Atlas verifies that file's `plan_sha256`, resolves the selected case from
the plan, obtains partition/source group from that plan, reconstructs the deterministic AP02
`ContextSourcePackage` from the persisted `EngineeringDocument`, persists it through the existing
hash-addressed private repository, and derives review class/predicate choices from the same formal
ontology `extraction_vocabulary` used by productive source extraction. An empty `cases` list builds all
planned Development/Holdout cases; an explicit list can select a smaller review package and optionally
bind a Development proposal. Holdout proposals remain rejected by default.

The correction also closes a cross-series hash defect: S08 previously calculated
`source_package_sha256` with a JSON digest that did not include the canonical newline used by the AP02
source-package repository. Review packages now use the existing
`context_source_package_content_sha256()` contract, so persisted AP02 package hashes, S08 review
bindings and the Series-E Development experiment allowlist agree exactly. The serialized S08 review
package contract itself is unchanged, so existing Series-E MCP/Codex readers require no parallel path
or compatibility alias. Previously prepared S08 packages should be rebuilt before using them as
Series-E Development authority.

A minimal corrected build manifest is therefore:

```json
{
  "contract_id": "assertion-review-workbench-build-v1",
  "id": "ap03-review",
  "version": "1",
  "corpus_plan": "partition-and-exposure.json",
  "ontology_versions": [
    "standards-atlas-core@2.0.0",
    "functional-safety@2.1.0"
  ],
  "cases": [
    {"document_key": "ISO26262-10", "clause_id": "clause-6c47b353e379"}
  ]
}
```

`corpus_plan` is resolved relative to the build manifest. Source packages are written below the
selected `--workspace` by the existing private repository; no model call is performed.

Correction verification used the already installed Python 3.13 environment and no model/network
calls: the combined assertion-qualification, Series-E MCP/Codex, Review/Web, CLI, architecture and
AP01/AP02 integration regression set reports **379 passed, 4 skipped**; the schema suite reports
**369 passed**. The skipped tests are existing optional-runtime cases. `uv run --offline ruff check`
was attempted, but dependency resolution stopped before Ruff because `jsonschema` is not present in
the local uv cache and network access is unavailable. Ruff therefore remains explicitly not executed;
the full project pytest suite remains for the user's local verification.

## S09 — server-side Development-only MCP exposure

A dedicated `profile: ap03-development` is added to the existing MCP server. It fails closed unless
it has a non-empty document allowlist, one or more explicitly registered S08 assertion-review
packages, disabled Holdout assistance, text exposure enabled for the selected Development sources,
no source-path exposure, and no legacy review/formula mutation capability.

The effective source authority is built server-side from the exact source surfaces of the registered
S08 **Development** cases. The same resolver also inspects reserved Holdout cases before startup and
rejects any Development/Holdout overlap in source-clause IDs, source groups or source-package hashes.
Document-level permission alone is therefore insufficient for a mixed Development/Holdout document.
Generic list/search/sample operations are evaluated only over the resolved Development source IDs and
do not delegate broad enumeration/search to the underlying corpus provider. Generic clause payloads
strip document-wide reference/context routing that could reveal an unapproved source; the exact
bearing context remains available only through the source-bound Development review case.

The AP03 profile registers no MCP resources and no table/formula/media tools. Its review projection is
S08 task-specific, Development-only and has no Human-confirmation or publication write. Experiment
reads use only explicitly registered experiment IDs and revalidate `partition=development`, data route,
case identity and source-package hashes against the same Development authority. Private raw-attempt
paths/messages and authorization references are not returned. Comparison reads use a fixed path;
client-supplied report/file paths do not exist. Symlinked review/experiment/report/staging paths are
rejected.

`mcp codex-config --server-config ...` now derives `enabled_tools` from the exact tools registered by
the selected server profile. The client allowlist is therefore an additional fence, not the security
boundary. `mcp probe --server-config ...` likewise binds its expected tool/resource surface to the
profile; the scoped profile is expected to have no generic documents resource.

## S10 — controlled Codex optimization handoff

Codex optimization is a separate MCP client role, not `CodexCliLlmGateway`. The single Development
write tool, `submit_prompt_variant_proposal`, accepts a narrow schema: one hypothesis, at most three
Development diagnostic clusters and exactly one replacement of the extractor **role system prompt**.
Extra fields are forbidden, so a proposal cannot submit Golden/evaluator/schema/source-policy/model/
partition/budget controls through this contract.

Atlas resolves the referenced experiment itself and requires an explicitly authorized Development
manifest. It verifies the exact manifest hash, base prompt, registered cases/source packages, data
route and existing call budget. Staging is server-owned and restricted below
`local/evaluation/assertions/ap03`; the client supplies no filesystem path. The new version must use a
`codex-*` identifier. Atlas copies the existing task schema and source-bound user template, preserves
policy/example bindings, validates the resulting bundle with the existing `PromptRepository`, marks
it `unqualified-development`, writes a hash-bound receipt, and makes an identical request idempotent.
No inference is started by this write.

The existing experiment plan/run/resume operations can consume a staged `codex-*` bundle only when the
operator explicitly supplies its bounded `--prompt-staging-root`. Planning still performs zero model
calls, and execution still requires the existing experiment authorization/budget checks. The staged
receipt names only these existing operations; it does not create a second runner.

`CodexCliLlmGateway` remains a different, optional direct-inference adapter. Its direct inference arm
is disabled by default. An explicit non-qualifying opt-in additionally requires an explicit model and
rejects seed, max-tokens, reasoning and non-default temperature because this CLI adapter does not
actually pass those controls. Unsupported parameters were removed from its request hash and are
reported as uncontrolled rather than being presented as effective reproducibility inputs.

`mcp codex-client-probe` checks the actual Codex executable. A real MCP tool-read happens only with
`--allow-synthetic-model-call` **and** an explicit `--model`; it generates an isolated temporary MCP
config whose only enabled tool is `get_server_info` while preserving an existing file-backed Codex
login by reference rather than copying credential bytes. The prompt expressly uses no standards text
and the client runs outside the project workspace. A server handshake or generic `mcp probe` is not
reported as successful Codex client tool recognition.

See `docs/development/ap03-codex-workflow.md` and `cfg/mcp-ap03-development.example.yaml` for the local
operating sequence.

## Series-E tests and execution status

Executed with the locally installed Python 3.13 packages, without model/network calls:

- S09 configuration/source/review protection set: 12 passed; the FastMCP registration test is skipped
  when the optional `mcp` package is unavailable.
- S10 prompt-staging contract: 3 passed.
- Experiment and assertion CLI regression after staged-prompt integration: 17 passed.
- Codex client/gateway/CLI tests: 11 passed.
- MCP compatibility/profile and CLI probe/config tests: 24 passed.
- final combined assertion-qualification/MCP/Codex/CLI/architecture regression: **356 passed,
  4 skipped** (optional MCP runtime unavailable);
- AP01/AP02 offline assertion/source-bound/schema integration regression: **95 passed**.

`uv run pytest ...` was attempted first. `uv` could not resolve the missing `chromadb` dependency
because this environment has no DNS/network access, so that invocation did not start pytest. The same
available test subsets were then run with `PYTHONPATH=src python3.13 -m pytest` using already installed
packages. The optional `mcp` package and `codex` executable are not installed here. No real client or
model run is claimed. Ruff is not installed in the local interpreter and `uv` cannot resolve the dev
environment, so Ruff remains for the user's local verification together with the full pytest suite.

## Handover to Series F

Series E ends at S10. The next permitted work is AP03-S11 followed by S12. Before any real run, rebuild
any previously prepared S08 review packages with the corrected plan-bound build path above, then use
the registered Development packages and an explicitly authorized experiment/data route/budget.
Generate and inspect the AP03 MCP profile from those real registrations; if Codex will be used as an
optimizer, perform the real client tool-recognition probe only with an approved provider route and the
synthetic/text-free probe. Series F may then run B0/P1/P2 and at most the bounded Development prompt
variant(s). Holdout remains inaccessible and must not be used for optimization. No S11/S12 model
result is part of this Series-E delivery.

---

## Preserved Series-D and earlier history


# AP03 status — Series D / S01-S08 complete

Date: 2026-10-03. Series D implements only AP03-S07 and AP03-S08 on the supplied, locally
verified post-Series-C snapshot `standards-atlas-current-202610030420.zip`. Series E is not started.

No real model, remote LLM, Codex client, private standards corpus or semantic-quality experiment was
executed in Series D. All new selection/review tests use public synthetic inputs. No human review
decision or Golden content was invented by the implementation.

## S07 — grouped reference corpus, partition and exposure contract

Series D adds `assertion-reference-corpus-plan-v1`, a text-free planning contract that separates
corpus selection from semantic truth. Candidate clauses declare their primary source group and every
source group that can carry their interpretation. The planner computes transitive connected source
groups before partitioning; Development and Holdout therefore cannot split a target from a shared
introduction, exception or other declared bearing context.

The exposure register records legacy Development use, AP02 synthetic use, prior review, prompt
examples, optimization/diagnosis/Codex exposure and unknown exposure explicitly. Any such exposure
blocks an independent-Holdout claim for the complete connected group. The historical 20-case
Development set and AP02 synthetic references are thus provenance, never silently relabeled as
Holdout. Selection is deterministic for identical candidates/seed and combines source-group
disjointness with declared diversity traits. Ineligible cases and shortfalls remain explicit blockers.
Every selected new case has `expected_status=pending`; partition creation itself cannot publish labels.

A new CLI operation `evaluation assertion-reference-corpus-plan` consumes an explicit JSON request and
writes `partition-and-exposure.json`. It does not inspect arbitrary user directories, run a model or
create Golden knowledge.

## S08 — task-specific Entity/Assertion review in the existing Workbench

The existing loopback Review Workbench now recognizes task-specific assertion packages alongside the
existing applicability packages. It reuses the same HTTP application, signed server view receipts,
Origin/CSRF middleware, reviewer binding and optimistic revision checks; no second web platform was
introduced. Applicability review behavior remains available unchanged.

Assertion review is source-first. A case exposes the exact bound AP02 source-package surfaces and keeps
a Development model proposal as a separate, collapsible preparation view. Holdout proposals are hidden
by default. Review editing uses human-readable Entity/Assertion IDs, ontology-bound class/predicate
choices, explicit endpoints and normative force. Browser text selection records quote/source identity;
Atlas resolves the quote against the canonical bound source surface, rejects ambiguous/nonexistent
quotes and computes offsets/hashes server-side. Entity evidence is retained in the review decision even
though the current Golden-suite contract evaluates assertion evidence only.

The decision model distinguishes `confirmed`, `corrected`, `deferred`, `rejected` and an expressly
confirmed empty Entity/Assertion result. Deleting/changing an Entity is validated through the existing
case-local endpoint integrity rules before a decision is accepted. A JSON `human_attested=true` value
alone has no authority: assertion writes additionally require the signed server view to contain the
Workbench human origin, exact package/state revision, case and reviewer identity. Stale revisions and
forged origins are rejected. Model proposals never write this state.

Publication is a separate operation over the persisted human state.
`evaluation assertion-review-workbench-publish` emits an `AssertionGoldenSuite` only for genuinely
confirmed/corrected cases; pending/deferred/rejected cases remain unpublished. The original Series-D
build input used already-bound source-package files and explicit ontology options; the post-Series-E
correction documented above supersedes only that preparation input and leaves the persisted review
package/publication contract unchanged. Neither operation adopts `DocumentKnowledge` or enables
canonical knowledge adoption.

## Series-D tests and execution status

Executed in this implementation environment:

- new S07/S08 unit tests: **6 passed**;
- assertion qualification + assertion CLI + existing web adapter + architecture regression set after
  CLI integration: **300 passed**;
- earlier assertion qualification + web adapter + architecture regression set: **292 passed**;
- existing AP01 assertion review-pilot regression before the new tests: **21 passed**;
- JavaScript syntax check for the modified Workbench `app.js`: **passed** using `node --check`.

`uv run --offline ruff check ...` was attempted. `uv` created `.venv` but dependency resolution could
not find `jsonschema` in the local cache while network access is disabled. Therefore Ruff did **not**
run and no Ruff success is claimed. The full project pytest suite was not executed; the user will run
Ruff and the full suite after applying the delta. No genuine model/client/private qualification run was
performed.

## Handover to Series E

Series D ends at S08. The next allowed work is AP03-S09/S10. Series E may expose these task-specific
review/read contracts only through an explicitly scoped Development MCP profile; it must not infer that
`local/` itself is an access boundary or expose Holdout source surfaces/proposals through indirect reads.
No S09/S10 functionality is included here.

---

## Preserved Series-C handover/history


Date: 2026-10-03. Series C implements only AP03-S05 and AP03-S06 on the supplied, locally verified
post-Series-B snapshot `standards-atlas-current-202610022211.zip`. Series D is not started.

No real model, remote LLM, Codex client, private standards corpus or semantic-quality experiment was
executed in Series C. All inference behavior exercised by the implementation tests uses Fake gateways
and public synthetic inputs. P1/P2 remain unqualified Development variants; B0 remains unchanged.

## S05 — bounded plan/run/resume and immutable attempt provenance

Series C adds a transport-neutral experiment application inside the existing assertion-qualification
boundary. It deliberately composes the existing productive components instead of introducing another
extraction engine:

- planning builds and persists the existing AP02 `ContextSourcePackage`, compiles the actual
  productive source-bound request and binds its SHA-256 per case without calling a gateway;
- Run/Resume delegate each experiment cell to the existing `KnowledgeProposalExtractionService` and
  `OntologyGuidedKnowledgeProposalExtractor` over the configured `LlmGateway`;
- successful native `DocumentKnowledgeProposal` objects use the existing proposal repository;
- no scheduler, model daemon, alternative parser, alternate proposal type or model process manager is
  introduced.

The versioned schema-1 experiment manifest binds experiment/code identity, variant, partition and
Golden-suite hash, ontology versions, prompt/task schema, exact source-package/request identity,
model route/runtime-config hash, requested parameters, repetitions, technical retries and absolute
call/token/runtime budgets. Planning is model-free and is **not executable by default**. Execution
requires `execution_authorized=true` plus a non-empty authorization reference; the implementation
therefore does not invent or silently assume the H1 plan/data-route/budget decision.

The AP03 attempt gateway enforces source/request identity and remaining budget immediately before the
delegate call. Every started call first receives an immutable attempt ID and an `outcome_unknown`
ledger entry. A completed call then records its distinct outcome, effective model/provider where the
gateway reports them, duration/usage where available, cache state and raw-response hash. Timeout,
context-limit, response error, model unavailability, parser/validation failure, budget block, unknown
remote outcome and rejected cache replay remain distinct.

Retries are limited to configured technical timeout/unavailability retries and always create a new
attempt. Validation/semantic outcomes are never retried until a preferred answer appears. Fresh
repetitions reject a cached gateway result rather than counting it as a new inference. Resume skips
completed cells. An interrupted call whose remote outcome is unknown remains visible and is not
silently replaced as though exactly-once generation had been proven.

Exact request/raw-response/parser-detail payloads are stored only below the private
`.atlas/data/assertion-experiments/<experiment>/attempts/` area. Directories are created with `0700`
and files with `0600`; the public `local/evaluation/assertions/ap03/...` manifest/state/report surface
contains status, bindings, hashes and text-safe diagnostics instead of protected raw bytes.

Implemented CLI operations are:

- `evaluation assertion-experiment-plan`
- `evaluation assertion-experiment-run`
- `evaluation assertion-experiment-resume`
- `evaluation assertion-experiment-report`

The CLI execution composition currently supports the existing `openai-compatible` route; other
registered compositions must use the same application service rather than creating a second runner.
Series C itself did not invoke that real route.

## S06 — existing evaluator plus stage-aware comparison

S06 keeps `AssertionQualificationEvaluator` as the only semantic Golden matcher/evaluator. The
experiment report loads the persisted native candidates for one repetition and passes them, together
with their actual source packages, to that evaluator unchanged. Multiple successful attempts for one
case/repetition are rejected instead of selecting the best result.

The versioned comparison envelope adds observations that the evaluator does not own:

- fixed selected/planned/attempted/technically-completed/failed/not-executed coverage;
- parser/grounding/other candidate rejection and transport-stage failures;
- actual call count, cache count, token usage and duration where the gateway exposes them;
- `unknown`/`null` rather than invented zero cost or usage;
- text-safe open diagnostics and review questions derived from actual report differences.

Failed, blocked or not-executed cells remain in coverage and cannot disappear to improve reported
quality. A genuinely empty native proposal remains distinguishable from transport/parser failure or
absence of output. Diagnostic editing does not recompute strict scores, and Series C adds no fuzzy
matcher, LLM judge or alias path.

## Schema / persistence decisions

Three lifecycle-crossing AP03 artifacts are registered in the existing schema governance instead of
being local ungoverned markers:

- `assertion-experiment-manifest` — `local/evaluation/assertions/ap03/**/experiment-plan.json`;
- `assertion-experiment-state` — `local/evaluation/assertions/ap03/**/experiment-state.json`;
- `assertion-experiment-report` — `local/evaluation/assertions/ap03/**/comparison.json`.

All three start at schema family version 1 and use `SchemaBoundModel`. Historical AP01 audit bytes,
v8 proposals, confirmed Golden IDs/`expected` contents and the AP01 metric contracts are unchanged.

## Test status

Tests executed in this implementation environment:

- S05/S06 experiment unit tests: **9 passed**;
- focused experiment + schema architecture check after governance integration: **99 passed**;
- final assertion-qualification / source-bound extraction / extractor-verifier adapter / assertion CLI
  / full architecture set: **329 passed**;
- focused integrations (`assertion_qualification` offline regression, AP02 source-bound E2E and
  context-scope transport): **14 passed**.

An earlier broad architecture run before the explicit schema-family integration reported exactly one
failure: the new experiment manifest carried `schema_version` without an architecture decision. That
was treated as an implementation defect, fixed by registering all three persistence contracts, and
the subsequent 99-test and 329-test sets passed.

`uv run ruff check .` was attempted. `uv` created a local environment but dependency resolution
could not reach PyPI because DNS/network access is unavailable; the command ended while fetching
`pyyaml` and therefore produced **no Ruff result**. This is recorded as not completed, not passed.
The full project `pytest` suite was not run here; the user will run Ruff and full pytest after
applying the cumulative delta.

No real model/client run, private qualification run or semantic model-quality measurement was
performed. No Golden, Holdout, `DocumentKnowledge` or human review decision was generated.

## Retained Series-A / Series-B baseline

Series A established the model-free preflight, experiment/release contract, frozen B0 and one
versioned productive task/prompt/schema path. Series B added the shared R01-R14 engineering policy,
unqualified P1/P2 resources and the source-bound Workbench path that uses the same productive
request/parser/grounding functions. B0 remains byte-stable and the legacy active
`formal-semantic-knowledge-extraction` entities/relations task remains removed.

## Handover to Series D

Series C ends at S06. The next allowed implementation is S07, followed by S08 if scope remains
manageable. Series D may consume the bounded experiment/report contracts for source-group-aware
Development/Holdout preparation and task-specific HITL, but must not reinterpret the Series-C public
state as human confirmation or qualification evidence. Historical Golden contents remain immutable;
new expected content remains pending until genuine human review. No Series-D functionality is
included in this delivery.
