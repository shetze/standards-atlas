# Engineering extraction qualification contract — AP03

Status: AP03 technical contract through Series H, 2026-10-04. Series C introduced the bounded
experiment runner described below; later series bind review, optimization access, measured Development
preparation, verifier/freeze readiness and the isolated Holdout completion path to that same runner and
evaluator. The supplied post-Series-G snapshot still lacks the real evidence/H3 confirmation required
to execute Holdout, so AP03 is technically implemented through S16 but is **not** experimentally
completed or qualified for a bounded pilot in this delivery.

## 1. Purpose and fixed baselines

AP03 measures the source-bound engineering-oriented Entity/Assertion extraction path. Two baselines
remain distinct:

- **V8-Audit** is the historical AP01 replay of unchanged stored v8 proposals against the confirmed
  20-case Development Golden. It is usable only when the original bound private artifacts are
  present and valid.
- **B0-AP02** is the frozen post-AP02 extractor/verifier request contract before AP03 semantic prompt
  optimization. Its packaged binding is `resources/semantic/prompts/ap03-b0.json`.

B0 fixes prompt text, output schemas and the post-AP02 source/context contract. It deliberately does
not pretend that a model declaration is an effective runtime identity. A later experiment must bind
its actual model/provider/runtime parameters separately.

The existing `AssertionQualificationEvaluator` remains the one semantic Golden evaluator. Strict
metrics, diagnostic interpretation, grounding integrity and exact Golden span comparison remain
separate concerns; later reports may reference the evaluator but must not recalculate a friendlier
score.

## 2. Model-free preflight

`evaluation assertion-ap03-preflight` performs only readiness and integrity inspection. It searches
fixed registered project locations for the historical AP01 inputs, validates the B0 packaged
resources and context contract, lists declared model configurations and emits release blockers. It
never searches arbitrary user directories, starts a model, downloads a model, accesses a network or
writes Golden/`DocumentKnowledge` state.

The current start snapshot does not contain the private AP01 audit/Golden/v8-report originals. Their
absence is therefore a normal explicit preflight gap, not a request to reconstruct them from status
documents.

## 3. Implemented bounded experiment contract (S05/S06)

Series C implements one transport-neutral experiment application around the existing productive
extractor and `LlmGateway`. Planning compiles the real source-bound request without a gateway call;
execution delegates clause processing to `KnowledgeProposalExtractionService` and persists native
`DocumentKnowledgeProposal` outputs in the existing proposal repository. The AP03 application does
not own a second parser, matcher or model process manager.

The versioned `assertion-experiment-manifest` binds plan/code identity, Development/Holdout
partition, Golden-suite hash, ontology versions, prompt/task schema, exact per-case source-package
binding and rendered request hash, model route/runtime-config hash, requested parameters,
repetitions, technical retry allowance and hard call/token/runtime budgets. A plan is model-free and
not executable by default. `execution_authorized=true` plus a non-empty authorization reference is
required before Run/Resume, so the implementation does not manufacture the H1 decision.

Immediately before every model call the gateway wrapper validates the rendered request identity and
the remaining budget. A token-bounded executable manifest must additionally bind a conservative
`max_total_tokens_per_call` reservation covering prompt plus completion; reserving only the requested
completion limit is not a hard total-token guard. The full reservation must fit before inference.
Known provider usage is charged at its observed total, while calls without usable token accounting are
conservatively charged at the reservation. A provider total above the reservation is a blocking budget
contract violation. Every started call gets an immutable attempt ID and an `outcome_unknown` ledger
entry that already carries the reservation before delegation, so Resume cannot regain budget after an
interrupted remote call. Success, timeout, context-limit, response error, unavailability, validation
failure, budget blocking/violation and rejected cache replay remain distinguishable. Technical
timeout/unavailability retries create new attempts; semantic/validation retries are not used to
search for a better answer. Fresh repetitions reject cached results. Resume skips completed cells
and never overwrites an interrupted attempt whose remote outcome is unknown.

Public experiment state contains hashes, status, usage/duration where available and sanitized
diagnostics. Exact requests, raw model responses and detailed parser errors are stored only in the
private `.atlas/data/assertion-experiments/.../attempts` area with restrictive filesystem
permissions. The public report never copies those protected bytes.

S06 passes persisted native candidates and their bound source packages to the existing
`AssertionQualificationEvaluator`. The versioned comparison report embeds that evaluator report
unchanged and adds fixed selected/planned/attempted/completed/failed/not-executed coverage,
stage-failure counts, observed effort and separate open diagnostics/review questions. Failed or
missing cells remain in coverage rather than disappearing from a score denominator. A repetition
with multiple successful attempts for one cell is rejected instead of choosing the best one.
Observed token usage remains `null` when any call lacks provider usage; the separate
`budget_charged_tokens` remains conservative and `unknown_usage_calls` makes that distinction
explicit. Unknown monetary cost stays unknown.

The implemented CLI surface is `evaluation assertion-experiment-plan`,
`assertion-experiment-run`, `assertion-experiment-resume` and `assertion-experiment-report`. Series-C
tests use only Fake gateways and synthetic sources; no real model or client execution is part of
this implementation delivery.

## 4. Release profile prepared for S14/S15

Concrete numeric quality limits are intentionally **unset** in Series A. They must be approved before
the Holdout campaign, not inferred after seeing its result. The eventual profile binds these gate
families:

- **G0 binding/access:** source, prompt, schema, ontology, model and partition identity plus an
  authorized data route.
- **G1 technical operation:** allowed failure/coverage limits and complete parser/grounding/endpoint
  integrity.
- **G2 engineering quality:** absolute primary-metric minima and minimum supports, including Work
  Products.
- **G3 critical semantics:** allowed scope for invented obligations, lost conditions/exclusions,
  wrong normative force and unjustified context copying.
- **G4 verifier/cascade:** false acceptance/rejection, missing-item detection, coverage and explicit
  unverified/unresolved states.
- **G5 stability/effort:** permitted run-to-run variation and call/token/runtime/review budgets; no
  best-of-N selection.
- **G6 Holdout/decision:** grouping/exposure rules, frozen campaign, evaluation policy and explicit
  human finalist/release decision.

Until those values, a frozen finalist, independent Holdout evidence and the required real runs exist,
the AP03 release state remains `not_ready_for_release`.

## 5. Evidence/status semantics

The following concepts must remain distinct in later reports:

1. **technically implemented** — software/contracts/tests exist; real sources or models may be absent;
2. **experimentally evaluated** — bound real attempts and comparison reports exist;
3. **qualified for the named bounded pilot** — approved gates and independent Holdout evidence are
   satisfied and the human release decision is present.

A successful schema parse, grounding check, fake-gateway test, server health check or verifier output
is not a semantic qualification result. Likewise a missing/failed output is not a correctly empty
semantic result.

## 6. AP03 invariants retained through Series C

- Historical audit bytes, stored v8 proposals, confirmed Golden IDs and `expected` contents are not
  modified or reconstructed.
- AP02 source-package, context, heading ownership and multi-span grounding contracts remain intact.
- B0 remains selectable in the normal versioned resource catalog; Series C does not alter B0/P1/P2
  prompt content.
- No real model or Codex client is invoked by Series C.
- No new Golden, `DocumentKnowledge`, adoption, RAG/GraphRAG or release-write path is introduced.


## 8. Series-H isolated Holdout and release boundary (S15/S16)

Series H adds no second semantic evaluator or optimizer loop. A `SeriesHHoldoutCampaign` fixes the
exact Holdout suite, partition/exposure state, G0-G6 gate profile, pre-authorized Finalist/baseline
experiment manifests, repetition counts and execution order before the final Series-G freeze. The
freeze binds the campaign hash. The model-free preflight rejects changed campaign/gates/partition,
exposed Holdout cases, manifest drift, non-Holdout manifests, missing execution authorization or a
code revision different from the freeze.

Execution delegates only to the existing bounded experiment runner; the optimizer client is not
invoked and no adaptive variant selection exists. Finalization materializes the existing native
proposals/source packages and calls the unchanged `AssertionQualificationEvaluator` for every planned
repetition. The release view adds pre-fixed technical, semantic/support and critical-finding gates
without recalculating friendlier semantic scores. Missing or failed cells remain evidence, and a
failed Holdout yields `evaluated_not_qualified` rather than a retuning request.

A passed Holdout is still not a release by itself. `qualified_for_bounded_pilot` additionally requires
an explicit human release reference and non-empty bounded scope. Canonical adoption is always disabled
by AP03; AP04 receives only bound identities and blockers from the generated handover and owns any
later knowledge-adoption decision.

For the 2026-10-04 supplied snapshot, the real Holdout is blocked before execution because the
Series-G handover reports missing real Development/verifier/repetition evidence and H3 confirmation.
The public Series-H E2E is therefore a synthetic software proof only. See
`ap03-series-h-quality-report.md` and `ap03-series-h-runbook.md` for the actual status and operation.
