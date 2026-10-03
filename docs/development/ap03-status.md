# AP03 status — Series E / S01-S10 complete

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
`--allow-synthetic-model-call` **and** an explicit `--model`; it generates a temporary token-free MCP
config whose only enabled tool is `get_server_info`. The prompt expressly uses no standards text. A
server handshake or generic `mcp probe` is not reported as successful Codex client tool recognition.

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
