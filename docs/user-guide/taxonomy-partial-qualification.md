# Final qualification and controlled activation (Slice 7)

This is an **opt-in qualification campaign**, not an automatic approval of a prompt, model,
acceptance profile or taxonomy rule. The ordinary qualification workflow, v2 default,
D4 OR (D3 AND D1) policy, required completion profile and public export rules are unchanged.
The campaign orchestrates the existing partial cascade and detail services; it does not
introduce another inference or consensus engine.

## What is being qualified

A campaign pins the complete source population, a reproducible proportional sample,
all published Applicability Golden cases, engineering sentinels and independently supplied
semantic development/holdout suites. It also pins matrix, prompt, profile, task, frame and
rule resources before any model run. Different prompt/profile combinations are declared
variants. Models, generation settings, stages, consensus and detail-policy configuration
must remain the same for a comparison.

The shipped example compares the current partial **B3 control** against a partial **B4
candidate**. Earlier B0/B1 structural replays and B2 full-output comparisons remain in their
existing qualification/replay workflows. They are not converted to fresh partial runs or
silently included in a common denominator. Use Slice 6's controlled prompt/profile comparisons
for causal ablations; the example campaign changes both prompt and acceptance profile.
This final campaign tests qualification readiness of the declared candidate as a whole.

Each declared variant runs three `fresh_end_to_end` and three
`fresh_detail_fixed_presence` repetitions. The latter reuse only that variant's independently
verified first End-to-End gate, never its detail responses. Repetitions remain separate
experiments and never add votes to the same consensus. Raising a matrix's repeat requirement
also raises the necessary campaign setting; a campaign cannot weaken it.

The suite requires, for **each candidate repetition**, final-policy FP <= 2, FN <= 2,
Missing = 0 and Unknown = 0 against the entire pinned published Golden set, with at least
116 cases and both positive and negative cases. Stricter existing FP/FN limits are preserved.
The literal number is a lower bound, not permission to discard additional published cases.
Planning, a stored audit, a copied job directory or an empty detail run is not a fresh pass.

## 1. Prepare sources and references

Copy/edit `cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml` before preparation.
Its paths follow **project-working-directory semantics**, not manifest-relative semantics.
Choose either `run` for an existing Qualification archive or `dataset` for a source dataset.
The complete source population is retained for the later full baseline.

Published Golden cases must exist in that population with matching document, clause and text.
Only a difference in trailing CR/LF line breaks is accepted and explicitly recorded; neither
source nor Golden text is edited. Other text drift or missing Golden cases is an error before
model startup. Existing `legacy-context` inputs remain hints; creating a campaign does not
confirm their authority. Use `require_taxonomy_decisions: true` on a variant when the proposed
experiment is specifically intended to demonstrate deterministic savings. It blocks before
inference when the selected source has no actual fixed decisions.

The representative sample uses document key and clause type strata, proportional largest-
remainder quotas and seeded content-hash ranking. Input order and labels cannot affect the
sample. Small strata can receive no slot; the selection report explicitly exposes that limit.
Golden, sentinels, development and holdout cases are unioned into the executed selection but
**reported as separate cohorts**. Do not call the unweighted union's completion rate a
representative population estimate. Cohort memberships can overlap; their totals are not to
be added. Holdout cannot overlap Golden, development or engineering-sentinel cases.

### Reviewed semantic suites

The [source-bound review-package workflow](partial-review-packages.md) now generates both
suite files from explicit human decisions, with original text, structure, fixed identifiers
and automated hash handling. Use it before campaign preparation instead of hand-authoring
reference YAML. Its source/context/rules evidence is copied into new campaign artifacts;
legacy unbound suites remain supported without that additional assurance.

The [archived review handoff](partial-review-handoff.md) now generates the complete suite pair,
review ZIP and a ready manifest. Use its `campaign.yaml` with the qualification workflow; a
review preflight runs before preparation and pins the archive in campaign artifact 1.2. No
manual copying of source hashes or suite paths is necessary. The explicit-suite example
below remains a supported legacy interface, not the recommended authoring procedure.


The example has `semantic_suites: []` on purpose: it can be prepared and explored, but it
**cannot qualify for full-baseline execution or activation** without reviewed semantic
coverage. Configure reviewed development and holdout suites before freezing the campaign.
For example, a JSON/YAML file follows this contract:

```yaml
schema_version: '1.0'
kind: partial-semantic-reference
id: independently-reviewed-holdout
version: '1.0.0'
split: holdout                 # or development
status: draft                 # published requires reviewer + review_reference
reviewed_by: null
review_reference: null
cases:
  - example_id: YOUR_EXISTING_CLAUSE_ID
    document_key: YOUR_DOCUMENT_KEY
    content_hash: sha256:REPLACE_WITH_THE_ACTUAL_64_HEX_CONTENT_HASH
    attributes:
      primary_function:
        equals: requirement   # example shape, not a supplied label
      process_functions:
        must_include: [activity]
```

These are deliberately placeholders, not a ready-made review or invented labels. Each check
uses exactly one operator: `equals` (including explicit null), `must_include` for a nonempty
list of labels, or `must_be_empty: true`. JSON scalar types remain distinct; false is not 0.
Provide both published splits with reviewed checks for Statement Primary, Knowledge Primary,
Role Presence and Process Functions. The default allows zero failed or unavailable semantic
checks; any changed budget must be explicit in the frozen campaign. The tool validates supplied
review provenance but cannot prove who performed it or whether a model saw the holdout earlier.

Engineering Process sentinels remain required regression checks, **not a replacement for
independent holdout gold**. Source hashes are verified. The synthetic taxonomy pilot remains
an integration test; its `fixture:` authority cannot qualify a production candidate. No
pending Requirement, Objective or Technique rule is approved by this command.

```bash
uv run standards-atlas evaluation partial-qualification-prepare \
  --manifest cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml \
  --output local/evaluation/taxonomy-efficient/slice-7/campaign
```

Preparation performs no inference. The output must be new and separate from all inputs.
It writes `campaign-plan.json`, `selection.json`, frozen inputs, source-only convenience
datasets and a pending `review.csv`. Labels and review fields never enter model datasets.
Editing that CSV does not modify authority or import new Golden labels.

`--reuse-frozen` is intended for the normal workflow resume path. It verifies the current
requested manifest, source and reference files, model matrices and profiles against the
stored campaign; it does not overwrite them. Changing the plan requires a new campaign.
A direct run/evaluation of the already frozen campaign does not require the original external
input paths to remain available.

## 2. Plan and run the independent repetitions

```bash
uv run standards-atlas evaluation partial-qualification-run \
  --campaign local/evaluation/taxonomy-efficient/slice-7/campaign
```

Without `--execute` this only lists planned jobs. With it, the existing model lifecycle is
used lazily and the RamaLama response cache is disabled for the qualification path:

```bash
uv run standards-atlas evaluation partial-qualification-run \
  --campaign local/evaluation/taxonomy-efficient/slice-7/campaign \
  --execute
```

`--variant ID` selects a declared variant. `--phase end-to-end` or `--phase fixed-detail`
can run one group; default `all` runs both groups, not the later full-population baseline.
Per-clause failures remain in their normal reports while other clauses and independent jobs
continue. `execution-report.json` shows interrupted/failed jobs explicitly. Completed jobs
are replay-verified on resume, not executed as extra repetitions. An interrupted job remains
the same repetition with its existing execution identity and recorded physical work.

Each job has its own `execution-identity.json`, `qualification-events/`, sealed `repeat.json`
and existing engine output under `run/`. Physical events record the complete request, result
hash, reported cache flag, usage when supplied, errors and actual call wall time. Cached replies
are rejected even from a custom gateway. Stored model responses must have corresponding fresh
physical events; counts reconcile with retries and gateway failures. Changing, moving or
copying a repetition cannot silently produce another fresh pass.

These are integrity and execution records, not cryptographic attestation of runtime model
weights or a guarantee that a remote server does not internally cache. Missing usage remains
unknown. Summed provider/request times are not process wall time. A job also reports its last
invocation wall time, which is explicitly incomplete after resume.

## 3. Evaluate and archive, without new model calls

```bash
uv run standards-atlas evaluation partial-qualification-evaluate \
  --campaign local/evaluation/taxonomy-efficient/slice-7/campaign \
  --archive-output local/evaluation/taxonomy-efficient/slice-7/archives
```

Every existing job is rechecked from source, original sparse observations, mixed consensus
and final policy, not trusted because a summary claims `passed`. The report contains paired
representative Efficient rates, cohort denominators, accepted source/value shapes, stage/model
failures, focused same-voter work, combined physical requests, reported tokens and downstream
policy outcomes. It separates missing evidence, invalid evidence and a valid run failing a
quality gate. Stable reports live under `evaluations/<evaluation-hash>/`.

The physical request ratio is candidate/baseline pooled over the same End-to-End repetitions
and includes focus plus detail work. The example's explicit 1.10 budget is an engineering
control, not a universal quality standard or a promise of lower latency. A useful candidate
must satisfy it or be tested under another predeclared campaign budget, not retrospectively
be called faster because its stage name changed.

`--fail-on-rejection` returns code 1 after writing the report, for CI/release use. It does not
make individual inference jobs fail-fast. Incomplete/rejected campaigns can still be archived
with the existing checksummed Qualification archive envelope, including raw evidence and
blockers. Audit-only historic reports cannot supply fresh qualification receipts.

## 4. Run the full baseline only after the small quality gates pass

```bash
uv run standards-atlas evaluation partial-qualification-run \
  --campaign local/evaluation/taxonomy-efficient/slice-7/campaign \
  --phase full \
  --execute
```

This is a separate explicit phase, for the declared candidate only. It requires verified
control repetitions, all six passing candidate quality repetitions and the cost gate. It
executes the **complete pinned source population** with the same model/profile configuration,
retaining unresolved clauses and individual failures. Its existing Partial-Cascade archive
is written to the campaign's `archives/` and remains compatible with explicit
`document adopt-qualification`. Successful archival is not semantic approval of every clause.

Evaluate again afterwards. The full-population Efficient completion rate is the comparison to
80%, not an individual model's format-validity rate or the overrepresented Golden union.
The 80% objective is reported independently from semantic eligibility.

## 5. Controlled activation, never automatic defaults

```bash
uv run standards-atlas evaluation partial-qualification-activate \
  --campaign local/evaluation/taxonomy-efficient/slice-7/campaign \
  --output local/evaluation/taxonomy-efficient/slice-7/qualified-candidate \
  --reviewer 'ACTUAL_REVIEWER' \
  --review-reference 'ACTUAL_APPROVAL_REFERENCE'
```

Activation first re-evaluates the raw evidence. It requires the small quality gates and a
verified, quality-passing full baseline. It exports an immutable bundle containing matrix,
optional profile, evaluation and `activation.json`, plus a concrete command template. No
repository manifest, prompt default, source authority, rule qualification or public enrichment
is changed. The profile's underlying experimental schema is not falsified as `qualified`;
the separate scoped evidence bundle is the qualification recommendation.

A semantically eligible, useful profile below 80% requires explicit `--allow-below-target`.
Its target remains **not reached**. This is not a bypass for failed Golden, semantic, freshness,
source or cost gates. The recommendation is scoped to the pinned population and supplied
review. A new corpus still needs an applicability/review decision.

## Existing workflow entry point

The existing qualification task recognizes the new `partial_qualification` manifest type:

```bash
uv run standards-atlas workflow run \
  --task qualification \
  --manifests cfg/evaluation/partial-cascade/qualification-campaign-v1.yaml
```

Use that manifest alone; the existing `standards`/`qualification_matrix` manifests and their
old workflow remain unchanged. The plan uses the existing corpus, matrix and archive stages:
prepare/resume, run independent repetitions, evaluate/archive. It does **not** automatically
run the gated full baseline or activate a candidate. `workflow plan` prints exact paths.
Sampling, repetitions and population are defined by the campaign, not by a second CLI limit.
The explicit phase commands above are also usable independently.

## Evidence boundaries

This slice implements and tests the workflow; it does not execute real local models inside a
code-delivery test. A passing simulated integration test is not a fresh production repetition.
No error budget is improved by discarding an unresolved case, inventing a semantic label,
weakening Primary/Set validation or treating an Applicability gate as the final policy.
