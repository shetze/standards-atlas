# Partial cascade readiness (Slice 5.1)

This slice makes the existing partial cascade reproducible and diagnosable before
changing acceptance profiles or adding resolvers. It does **not** change model rosters,
confidence thresholds, strict grouped validation, the Applicability detail formula,
source authority or public enrichment omissions. It does not demonstrate a production
80% Efficient exit rate.

## Choose the effective partial prompt explicitly

`evaluation partial-cascade` now accepts `--prompt`. The full-output prompt in the input
matrix is not the partial prompt. Supported cascade choices are:

| Partial prompt | Purpose |
|---|---|
| `taxonomy-partial-v2` | Existing default and reproducible control. |
| `taxonomy-partial-v3` | Complete-set contract candidate; known Process Function concern. |
| `taxonomy-partial-v3-no-process-null` | v3 with only its Process-null shape example removed. |
| `taxonomy-partial-v4` | The ablation plus independent, text-grounded Process Function boundaries. |

v1 remains supported by `partial-proposals`, but not by the cascade: it cannot carry all
accepted-attribute constraints. The two new prompts are **unqualified candidates**. Their
schemas are identical to v3. They do not gate Process Functions on the Knowledge Kind,
and do not force nonempty output when the text contains no process-model role. No default
is promoted on the basis of response format success alone.

For a bounded actual v4 candidate run on the historical first 50 clauses:

```bash
uv run standards-atlas evaluation partial-cascade \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --run local/evaluation/qualification-run-078.zip \
  --limit 50 \
  --prompt taxonomy-partial-v4 \
  --output local/evaluation/taxonomy-efficient/slice-5.1/run-078-50-v4 \
  --execute
```

Without `--execute` this only plans the first stage. Every comparison prompt requires a
**new output directory**. Keep the same clause selection and model/generation settings.
The prompt and its actual resources bind planning, requests, cache identities, resume,
stage revisions and archive/adoption verification. Changing a prompt in an existing run
is rejected before inference. Unchanged schema-1.1 default-v2 requests retain their
identities. In the independent cascade-run plan contract, an omitted prompt field means
v2, never the newest installed prompt; it does not authorize obsolete request schemas. The matrix suffix `--taxonomy-partial-v1` names the engine, not the prompt.

Use the ordinary archive option after a successful execution; archive verification
reconstructs the selected prompt and rejects mismatching requests/resources. A plain
planning invocation cannot overwrite an already executed report. Use the read-only audit
below to inspect an executed run without retrying failures.

## Read planning metrics correctly

The `partial-cascade-report` schema is **1.1 only**. Schema 1.0 is rejected on replay,
archiving and resume; there is no legacy metrics fallback. The independent cascade-run
and mixed-consensus families retain their versions. Every current report includes:

- `run_mode`: `planned` or `executed`, plus the existing `executed` flag;
- `effective_configuration`: actual task, prompt, frame, source-rule/resource fingerprints,
  and each stage's model/generation configuration;
- `completion_profile_eligible`: whether the required core attributes are present;
- `completion_rate: null` and `benchmark_eligible: false` for planning only;
- `measurement_status: observed_not_qualified` after execution, not a semantic qualification;
- accepted `null`, `false`, empty sets and nonempty values counted separately.

`--execute` describes the invoked operational mode, not a fresh repetition guarantee.
A resumed execution may reuse observations with the current contract and exactly matching
source/request identity, not observations in obsolete formats. `fresh_repetition_qualification` stays false.
A synthetic fixture pilot is never benchmark-eligible even if its mock/inferred responses
complete every clause. Counts of accepted attributes are not counts of nonempty values.

## Audit existing complete cascade artifacts without inference

```bash
uv run standards-atlas evaluation partial-cascade-audit \
  --experiment local/evaluation/taxonomy-efficient/slice-5/run-078-50-v2 \
  --output local/evaluation/taxonomy-efficient/slice-5.1/audit-078-50-v2
```

`--experiment` must be the **actual complete run directory** or its complete ZIP/archive,
not just `partial-cascade-report.json`. The output must be new and outside that source.
No gateway, model server, acceptance changes or source writes occur. Active writer locks,
missing required files, unsafe archive paths and inconsistent evidence are rejected.
The tool reuses the existing source/request/observation/consensus replay verifier, including
failed-request bindings; it is not another voting implementation.

The JSON and Markdown reports contain per-stage cumulative and entered-clause denominators,
open required attributes, exclusive blockers, pairwise overlaps, exact combinations,
consistency reasons, original per-model values/support and accepting sources/stages.
They also distinguish:

- final logical model observations from failed/retired execution copies;
- gateway failures from post-gateway contract rejection;
- per-model schema/pair/role error families and affected attributes;
- additional attempts within an execution from repeated executions of a case;
- work in active revisions from work in retired revisions;
- cascade costs from any separately recorded Applicability-detail costs.

The counters reconcile recorded attempts with measured calls and gateway failures. Missing
observations are reported, not invented. `source_summary_timing_matches` checks request and
failure counts; it does not attest provider duration or full end-to-end wall time. No
Role-Presence minority is silently reclassified, and no threshold changes follow from an
audit. Applicability gate diagnostics are not final policy evaluation or Golden FP/FN.

## Build a usable source-readiness pilot

A taxonomy saving requires **both** confirmed source facts and a qualified narrow rule.
The installed rule profile still permits only `term-definition` to fix a primary. Other
rules remain pending; source confirmation alone does not release them. This slice does not
mislabel engineering examples as independent human approval.

To select a separate fixed/conflict/hint/open pilot from a newly built source dataset:

```bash
uv run standards-atlas evaluation taxonomy-pilot \
  --dataset path/to/new-source-corpus/dataset.json \
  --limit 24 \
  --output local/evaluation/taxonomy-efficient/slice-5.1/source-pilot
```

Build that source corpus through the existing `evaluation corpus-build --source-only-context`
path, described in [Taxonomy-grounded qualification](taxonomy-grounded-qualification.md).
Use the dataset path actually returned by that command. Existing canonical confirmations
are preserved. No old inferred value, structural hint, semantic label or model majority is
promoted to independent source authority. `--run` accepts historical archives for diagnosis;
Run 078 can correctly produce zero fixed decisions.

The pilot writes `dataset.json`, `pilot-readiness.json`, `source-review.csv` and a README.
Selection round-robins fixed/conflict/hint/open cases; it is intentionally **not** a
representative accuracy or 80% sample. Gold/expected fields are stripped from model inputs.
The review CSV retains text, source facts, rule/source hashes and pending reviewer fields.
It is a review asset, **not** an approval importer. New rule releases still require a
separate documented domain review and versioned qualification.

A safety check is available on `partial-cascade`:

```bash
uv run standards-atlas evaluation partial-cascade \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --dataset local/evaluation/taxonomy-efficient/slice-5.1/source-pilot/dataset.json \
  --prompt taxonomy-partial-v4 \
  --require-taxonomy-decisions \
  --output local/evaluation/taxonomy-efficient/slice-5.1/source-pilot-v4
```

This is a planning call. The optional guard fails **before model startup and run writes**
when no qualified fixed attribute exists. It does not turn hints into fixed decisions or
change the completion profile. Add `--execute` only for a deliberate inference run. Omit
the guard for a deliberately historical control, not to pretend it tests taxonomy savings.

### Synthetic integration control, clearly separate from domain evidence

```bash
uv run standards-atlas evaluation taxonomy-pilot \
  --synthetic-smoke \
  --output local/evaluation/taxonomy-efficient/slice-5.1/synthetic-pilot
```

The twelve constructed `ATLAS-PILOT` clauses use the real canonical source-projection path.
Only three Term examples have explicit `fixture:taxonomy-readiness-v1` type authority and
therefore fixed definition primaries. There is also a Work-products/Objective conflict,
unconfirmed Terms, technique activities, an output, an input requirement, genuine negative
headings and a normative Applicability note. The resulting first-request plan asks 105 of
108 possible attributes. Expected results live in a separate `readiness-checks.json`, never
in the dataset's model context. Test fixture authority is not independent domain review.

This controls the engineering chain fixed → omitted question → mixed acceptance → early
exit. It cannot estimate how often real standards qualify for the same path.

## Check Process semantics separately from format

Five source-bound sentinels from supplied Run 078 require, respectively, a work product
(output), a validation objective, two explicit activities, and an empty set for a bare
bibliography heading. Their text and content hashes are pinned. They are scoped engineering
checks with **pending independent review**, not a replacement for published Golden data.

On an existing `partial-audit` report from a single-model experiment:

```bash
uv run standards-atlas evaluation semantic-readiness-evaluate \
  --audit local/evaluation/taxonomy-efficient/slice-4/audit-078-v3/partial-audit.json \
  --checks src/standards_atlas/resources/semantic/qualification/process-functions-sentinels-v1/checks.json \
  --output local/evaluation/taxonomy-efficient/slice-5.1/process-v3-checks
```

The model-free evaluator compares original response values against source-bound expectations.
It reports passed, failed and unavailable separately, as well as whole-observation contract
validity. An invalid/unrequested/missing Process field never counts as a negative. A process
sentinel may pass even when an unrelated pair invalidates the whole response; this does not
salvage any field into the cascade. No check pass releases a taxonomy rule.

For a controlled new single-model comparison use the existing `partial-proposals --prompt`
command with v3, the ablation or v4, a distinct output per arm, and identical input/model
settings. Generate its `partial-audit` and evaluate the same checks. Prefer the complete
first-50 historical comparison plus these checks over selecting only favourable examples.
The synthetic pilot can additionally use its own separate readiness-checks file. A formal
fresh-repeat semantic qualification remains a later step.

## Final qualification and activation

See [the final qualification campaign](taxonomy-partial-qualification.md) for pinned
cohorts, independent fresh repetitions, explicit full baselines and reviewed activation.
Candidate availability or a passing integration test alone never promotes a profile.
