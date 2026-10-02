# Engineering extraction qualification contract — AP03

Status: Series-A contract baseline, 2026-10-02. This document defines the information that later
AP03 experiment/release artifacts must bind. It does **not** execute an experiment, choose quality
thresholds, qualify a model or create a second evaluator/runner.

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

## 3. Experiment-plan contract prepared for S05

S05 will implement the runner/ledger. Its manifest must not be weaker than this Series-A contract.
A plan is executable only when the following information is explicit and internally bound:

| Area | Required information |
|---|---|
| Plan identity | Contract/version, plan ID/revision, creation provenance and code/delivery revision. |
| Data route | Source repository/authorization class, permitted text route, Development vs Holdout purpose and privacy classification. |
| Partition | Suite/corpus/partition identity, source/grouping/exposure manifest and exact case selection. |
| Source contract | Per-case source-package identity/fingerprints, context-selection policy and required source availability. |
| Prompt/schema | B0/P1/P2 (or later approved variant) bundle, task schema, ontology versions and rendered request identity. |
| Model route | Provider/backend/client/model/artifact identity where available; requested versus effectively supported parameters must be separate. |
| Budgets | Absolute maxima for selected clauses, variants, repetitions, calls, technical retries, input/output tokens where enforceable, elapsed runtime and optional monetary cost. Verifier/escalation/warm-up calls count when present. |
| Reuse/repetition | Complete experiment identity for reuse; cache replay and new inference are distinct; new-inference repetitions cannot reuse the same cached response. |
| Primary metrics | Existing entity/assertion/class/predicate/force/exact-match metrics plus four Work-Product metrics with supports. |
| Technical coverage | Selected, eligible, attempted, technically completed, verified, unresolved and not-executed counts; schema/parser/ontology/grounding errors remain separate. |
| Critical semantics | Predeclared treatment of invented obligations, lost conditions/exclusions, wrong force and unjustified context transfer. |
| Holdout use | Whether Holdout is planned, its frozen campaign identity, exposure status and prohibition of adaptive optimization from intermediate results. |
| Human decisions | Required H1/H2/H3 decisions and the exact state that is pending; model output never represents human attestation. |

Missing required fields block execution or release as appropriate; they are not silently filled from
a model name, current directory, default provider or historical report.

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
the only Series-A release state is `not_ready_for_release`.

## 5. Evidence/status semantics

The following concepts must remain distinct in later reports:

1. **technically implemented** — software/contracts/tests exist; real sources or models may be absent;
2. **experimentally evaluated** — bound real attempts and comparison reports exist;
3. **qualified for the named bounded pilot** — approved gates and independent Holdout evidence are
   satisfied and the human release decision is present.

A successful schema parse, grounding check, fake-gateway test, server health check or verifier output
is not a semantic qualification result. Likewise a missing/failed output is not a correctly empty
semantic result.

## 6. Series-A invariants

- Historical audit bytes, stored v8 proposals, confirmed Golden IDs and `expected` contents are not
  modified or reconstructed.
- AP02 source-package, context, heading ownership and multi-span grounding contracts remain intact.
- No semantic prompt optimization is performed; B0 remains selectable in the normal versioned
  resource catalog.
- No real model or Codex client is invoked by Series A.
- No new Golden, `DocumentKnowledge`, adoption, RAG/GraphRAG or release-write path is introduced.
