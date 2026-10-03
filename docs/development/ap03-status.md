# AP03 status — Series C / S01-S06 complete

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
