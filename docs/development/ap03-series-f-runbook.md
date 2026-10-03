# AP03 Series F — Development baseline and controlled prompt comparison runbook

Series F is Development-only. It uses the existing AP03 experiment runner and the unchanged
`AssertionQualificationEvaluator`; it does not introduce another matcher, Holdout access, Golden
mutation, or automatic knowledge adoption.

## 1. Preflight

Run the model-free preflight first:

```bash
uv run standards-atlas evaluation assertion-ap03-preflight \
  --project-root . \
  --output local/evaluation/assertions/ap03/series-f-preflight.json
```

Required before real Series-F execution:

- the original v8 review audit and published Development Golden suite in registered `local/review/assertions` paths;
- the private EngineeringDocuments/source-package workspace needed by the selected Development cases;
- an explicitly approved model/data route and budget;
- a reachable runtime matching the selected model route.

A declared model is not proof of runtime availability.

## 2. Historical v8 offline replay

When the original audit is available, replay it without generating new proposals and without
replacing the historical files:

```bash
uv run standards-atlas evaluation assertion-evaluate \
  --golden <development-golden-suite> \
  --review <original-v8-review-audit> \
  --output local/evaluation/assertions/ap03/<campaign>/v8-offline-replay.json \
  --summary-output local/evaluation/assertions/ap03/<campaign>/v8-offline-replay-summary.md
```

This is an offline evaluation of the stored v8 proposal snapshots in the original audit. It is not a
new v8 model run and must not be presented as a prompt-only causal comparison with AP03.

## 3. Prepare B0/P1/P2 with one-factor protection

Prepare the full Development comparison in one operation. This operation performs zero model calls.
The exact budget values, model route, model identity and authorization reference must come from the
approved experiment decision; do not copy the illustrative placeholders below.

```bash
uv run standards-atlas evaluation assertion-series-f-prepare \
  --suite <development-golden-suite> \
  --campaign-id <campaign-id> \
  --model-route <approved-model-route> \
  --model <approved-model-id> \
  --config cfg/llm.yaml \
  --workspace .atlas \
  --smoke-cases 3 \
  --repetitions 1 \
  --max-calls <approved-per-variant-call-budget> \
  --max-retries-per-case <approved-retry-budget> \
  --max-total-tokens <approved-token-budget> \
  --max-runtime-seconds <approved-runtime-budget> \
  --max-output-tokens <approved-output-limit> \
  --authorization-reference <approved-plan-reference> \
  --authorize-execution
```

The generated `series-f-plan.json` references a B0 smoke experiment (strict subset), then B0 full,
P1 and P2. B0/P1/P2 must share the same non-prompt-factor fingerprint. The preparation fails if the
Golden partition is Holdout, the full call budget is too small, or authorization is incomplete.

Prompt bindings are fixed by the implementation:

- `B0-AP02` → `ontology-guided-assertions-source-bound-v1`
- `P1` → `engineering-policy-v1`
- `P2` → `engineering-policy-contrast-v1`

## 4. Execute in the recorded order

Read `series-f-plan.json` and execute only its `execution_order`. Each referenced experiment is run
with the existing runner:

```bash
uv run standards-atlas evaluation assertion-experiment-run \
  --experiment-id <experiment-id> \
  --suite <development-golden-suite> \
  --config cfg/llm.yaml \
  --workspace .atlas \
  --project-root .
```

Use `assertion-experiment-resume` only for an interrupted experiment. The B0 smoke result is a
technical/semantic smoke observation and is not added to the full B0 statistics; the full B0 run has
its own manifest and attempts.

## 5. Report B0 and variants

Generate B0 first:

```bash
uv run standards-atlas evaluation assertion-experiment-report \
  --experiment-id <b0-full-experiment-id> \
  --suite <development-golden-suite> \
  --workspace .atlas \
  --project-root .
```

Then report P1/P2 against the B0 qualification report produced by that campaign:

```bash
uv run standards-atlas evaluation assertion-experiment-report \
  --experiment-id <p1-or-p2-experiment-id> \
  --suite <development-golden-suite> \
  --workspace .atlas \
  --project-root . \
  --baseline-report <b0-qualification-report>
```

The report keeps fixed coverage, technical failures, usage/runtime observations and the existing
strict evaluator metrics separate. Missing/failed outputs are not treated as correct empty results.
Do not loosen matching or edit Golden expectations in response to the comparison.

## 6. Codex Development diagnosis

Codex diagnosis is optional and restricted to Development. Before using it, the real S10 text-free
client tool-recognition probe must be green on the approved provider route. Codex may propose only a
small prompt change within the already approved search space. It may not access Holdout, alter Golden,
evaluator, schema, source policy, model route, budget or protection rules, and it may not write human
attestation or canonical knowledge.

If the real Codex probe is not green, complete B0/P1/P2 without Codex diagnosis or leave the optional
diagnosis explicitly open.
