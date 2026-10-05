# AP03 Series G runbook — S13/S14

Series G is Development-only. It measures the verifier on already persisted Development candidates,
closes cascade end states, executes only pre-authorized fresh repetitions, and freezes the candidate
and gates before Holdout. It does not mutate Golden expected content, expose Holdout to the
optimization client, publish canonical knowledge or claim qualification.

## 1. Run the verifier on the chosen Development candidate set

After Series F has a chosen Finalist/B0 experiment, reuse its persisted native candidates. Do **not**
rerun the extractor merely to create verifier observations. Before authorizing calls, make the approved
LLM endpoint available and check it with the same runtime configuration, for example:

```bash
uv run standards-atlas llm status --config <same-approved-llm-config.yaml>
# if required:
uv run standards-atlas llm start --config <same-approved-llm-config.yaml>
uv run standards-atlas llm status --config <same-approved-llm-config.yaml>
```

The verifier command itself also performs a read-only endpoint health preflight and aborts before the
first verifier call when the endpoint is unavailable. It loads the successful candidate cells from the
bound Development experiment, disables LLM result-cache reuse for the verifier benchmark, runs exactly
one verifier call per candidate clause, and writes two artifacts:

- `verifier-run.json`: actual verifier outcomes; keep this away from the reviewer while annotating;
- `verifier-review.csv`: blind, flat candidate review sheet with no verifier dispositions.

The command refuses Holdout suites/experiments and checks `max_calls` before the first verifier call.
Use a real authorization reference; the CLI never invents it.

```bash
uv run standards-atlas evaluation assertion-series-g-verifier-run \
  --campaign-id <series-g-campaign> \
  --experiment-id <series-f-finalist-experiment-id> \
  --suite <development-golden-suite.yaml> \
  --verifier-model <verifier-model-id> \
  --max-calls <authorized-call-limit> \
  --authorization-reference <H1-or-approved-series-g-reference> \
  --authorize-execution \
  --config <same-approved-llm-config.yaml> \
  --workspace .atlas/data \
  --project-root .
```

Default outputs:

```text
local/evaluation/assertions/ap03/<series-g-campaign>/verifier-run.json
local/evaluation/assertions/ap03/<series-g-campaign>/verifier-review.csv
```

Series G uses `ontology-guided-assertion-verifier-source-bound-v2` for this benchmark. The frozen
post-AP02/B0 verifier bundle `...source-bound-v1` remains byte-identical audit material. V2 changes only
the technical response contract: `entity_reviews` and `assertion_reviews` are schema-bound per request to
the supplied candidate counts and IDs, and the prompt requires byte-for-byte ID copying. Empty candidate
lists therefore require empty review lists. The existing post-response exact-ID validation remains active;
there is no positional fallback, silent repair or invented candidate mapping.

A verifier transport/response failure is retained in `verifier-run.json`; it is not silently removed
from later coverage. Candidate-ID contract failures likewise remain explicit verifier errors rather than
being coerced into reviews.

If a completed verifier run contains only technical verifier errors for a subset of cases, do not rerun
the successful cases. Retry only those errors with a **new campaign ID** and the same bound experiment,
verifier identity and runtime configuration:

```bash
uv run standards-atlas evaluation assertion-series-g-verifier-run \
  --campaign-id <new-retry-campaign> \
  --experiment-id <same-series-f-finalist-experiment-id> \
  --suite <same-development-golden-suite.yaml> \
  --verifier-model <same-verifier-model-id> \
  --max-calls <authorized-retry-call-limit> \
  --authorization-reference <approved-retry-reference> \
  --authorize-execution \
  --retry-errors-from local/evaluation/assertions/ap03/<parent-campaign>/verifier-run.json \
  --config <same-approved-llm-config.yaml> \
  --workspace .atlas/data \
  --project-root .
```

The retry command verifies that the parent manifest, variant, verifier provenance, runtime identity,
source-package hashes and candidate IDs/summaries still match. It then performs model calls **only** for
parent cases whose `verification` is absent and a verifier error is present. Existing valid verifications
are inherited unchanged. The merged retry artifact contains the complete case set, records its parent run
SHA-256, the retried case IDs and the inherited-case count, while `actual_calls` counts only the newly
executed retry calls. A parent with no technical verifier errors is rejected. This is a transport/response
retry, not semantic resampling or Best-of-N.

The retry produces a new blind CSV bound to the merged run hash. If source packages and candidate
identities are unchanged, previously completed human truth may be deterministically rebound to that CSV;
the Golden decisions themselves are not repeated or changed.

## 2. Human candidate truth and `verifier-observations.json`

Open only the blind `verifier-review.csv` for the H2-style verifier truth review. It contains one
`row_kind=case` row per clause followed by `entity`/`assertion` candidate rows.

For every **case row**, the reviewer must fill:

- `missing_entity_expected`: `true` or `false`;
- `missing_assertion_expected`: `true` or `false`;
- `annotation_reference`: a stable human-review reference.

For every **candidate row**, fill `expected` with exactly `supported` or `rejected`. Do not change the
run hash, identities, candidate IDs or summaries. The prepared CSV is deliberately flat because these
are candidate-disposition decisions, not nested Golden editing. The review does not publish or mutate
Golden content.

After review, build the observations by binding the human truth back to the hidden verifier outcome:

```bash
uv run standards-atlas evaluation assertion-series-g-verifier-observations-build \
  --verifier-run local/evaluation/assertions/ap03/<series-g-campaign>/verifier-run.json \
  --reviewed-csv local/evaluation/assertions/ap03/<series-g-campaign>/verifier-review.csv \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/verifier-observations.json
```

The importer rejects modified candidate identities, incomplete decisions and a CSV from another
verifier run. Verifier-call failures become observation errors and reduce measured coverage instead of
disappearing. They do **not** become semantic false acceptance, false rejection or missing-item false
negative observations. Candidate error cases are excluded from the corresponding rate denominators;
the metrics retain total annotated support, actually reviewed positive/negative candidate support,
annotated versus assessed missing-item-positive support, case/candidate/missing-item coverage and the
conservative overall coverage separately.

Now measure S13:

```bash
uv run standards-atlas evaluation assertion-series-g-verifier-evaluate \
  --observations local/evaluation/assertions/ap03/<series-g-campaign>/verifier-observations.json \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/verifier-metrics.json
```

Synthetic mutations may still be evaluated separately and combined only under their explicit
`synthetic_mutation` kind. They do not replace the real annotated Development support.

## 3. Optional bounded second-verifier factor

The default cascade leaves escalation output unverified:

```bash
uv run standards-atlas evaluation assertion-cascade ... \
  --leave-escalation-unverified
```

To measure exactly one extra verifier pass as a separate Development factor:

```bash
uv run standards-atlas evaluation assertion-cascade ... \
  --verify-escalation
```

An escalated clause is `technically_verified` only if the second pass completely reviews the
escalation candidates, detects no missing items and the escalation itself has no extraction failure or
violation. Otherwise it remains `needs_review` or `failed`. Do not turn this into a repair loop.

## 4. Fresh repetitions and `repetitions.json`

Use the existing `assertion-experiment-plan`/`run`/`resume`/`report` path for the selected Finalist and
any pre-authorized comparison configuration. Repetitions must be new inference attempts with cache
bypass. Do not choose a best attempt. Every newly authorized token-bounded repetition manifest must
bind both `--max-total-tokens` and `--max-total-tokens-per-call`; the latter is the conservative
prompt-plus-completion reservation enforced before each call. Historical Series-F manifests without
the reservation remain valid audit/report inputs but are not executable repetition manifests.

Once the individual repetition `comparison.json` reports exist, materialize their bound evidence:

```bash
uv run standards-atlas evaluation assertion-series-g-repetitions-build \
  --variant-id <finalist-variant-id> \
  --planned-repetitions <pre-authorized-count> \
  --report <repetition-1-comparison.json> \
  --report <repetition-2-comparison.json> \
  --report <repetition-3-comparison.json> \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/repetitions.json
```

Every completed repetition gets a file hash. Reports with cache use are counted as cached rather than
fresh. Distinct experiment IDs are required. The builder also reports case IDs whose qualification
result changed between repetitions; it never selects the best run.

## 5. Define G4/G5 before Holdout

The project owner must choose the gate values from the intended bounded pilot/risk policy, **not** from
future Holdout results. The CLI only materializes explicitly supplied values:

```bash
uv run standards-atlas evaluation assertion-series-g-gate-profile-build \
  --max-false-acceptance-rate <value> \
  --max-false-rejection-rate <value> \
  --min-missing-item-recall <value> \
  --min-verifier-coverage <value> \
  --min-real-annotated-cases <count> \
  --min-candidate-support <count> \
  --min-supported-candidate-support <count> \
  --min-rejected-candidate-support <count> \
  --min-missing-item-positive-support <count> \
  --required-fresh-repetitions <count> \
  --max-cached-repetitions 0 \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/gate-profile.json
```

At this stage omit `--human-confirmation-reference` if H3 has not yet happened. After the complete
freeze has been inspected, rerun the same command with the **same gate values** plus the genuine H3
reference:

```text
--human-confirmation-reference <H3-reference>
```

This records the decision; it does not authenticate or fabricate the human confirmation.

The three separate support minima refer to **actually assessed** semantic denominators. They prevent a
large aggregate candidate count from hiding, for example, a false-rejection rate based on only one or
two supported candidates. Technical verifier errors therefore remain visible through coverage and error
counts and cannot inflate or poison those semantic denominators.

## 6. Plan the future Holdout campaign without executing it

Before building the final Series-G freeze, follow Sections 2–4 of the Series-H runbook only far enough
to create the fixed Series-H gate profile, authorized Holdout experiment manifests and
`series-h-campaign.json`. This is model-free campaign preparation. Do not run Holdout and do not give
the optimizer access to Holdout sources or expectations.

## 7. Build the complete Series-G freeze

The freeze builder avoids manual hash maintenance. It reads the selected Development Finalist
experiment, the bound partition/exposure plan and the already prepared Series-H campaign. It derives
prompt/request, task-schema, ontology, source/context, model/backend, retry/budget and evaluator
identities from the bound manifest/current code, uses the plan's own `plan_sha256`, and uses the
Series-H canonical campaign hash. Canonical adoption is fixed off.

```bash
uv run standards-atlas evaluation assertion-series-g-freeze-build \
  --freeze-id <freeze-id> \
  --finalist-experiment <series-f-finalist-experiment-id> \
  --partition-plan <partition-and-exposure.json> \
  --holdout-campaign <series-h-campaign.json> \
  --leave-escalation-unverified \
  --workspace .atlas/data \
  --project-root . \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/freeze.json
```

Use `--verify-escalation` only if the bounded second-verifier factor was actually selected as the
frozen cascade policy. A functional code change after this step changes the code revision and requires
a new freeze.

## 8. Evaluate readiness

After verifier metrics, fresh-repetition evidence, the unchanged confirmed gate profile and the final
freeze all exist:

```bash
uv run standards-atlas evaluation assertion-series-g-readiness \
  --metrics local/evaluation/assertions/ap03/<series-g-campaign>/verifier-metrics.json \
  --repetitions local/evaluation/assertions/ap03/<series-g-campaign>/repetitions.json \
  --gate-profile local/evaluation/assertions/ap03/<series-g-campaign>/gate-profile.json \
  --freeze local/evaluation/assertions/ap03/<series-g-campaign>/freeze.json \
  --output local/evaluation/assertions/ap03/<series-g-campaign>/series-g-readiness.json
```

A blocker-free `ready_for_holdout=true` means only that the pre-Holdout prerequisites are bound. It is
not a qualification claim. Series H performs the isolated Holdout and final bounded release decision.
If verifier support, repetition evidence, H3, freeze identity or gates are insufficient, preserve that
negative/blocking result; do not retune against Holdout.
