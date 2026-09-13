# Experimental partial-cascade resolution (Slice 6)

Slice 6 adds **opt-in acceptance profiles**, a bounded first-stage refinement and
controlled comparisons. The existing engine, model identities, source-authority rules,
strict grouped response validation and public enrichment omissions remain in force.
The default is still `taxonomy-partial-v2` **without** an acceptance profile.
No shipped candidate has been declared semantically qualified.

## Separate the three experiments

1. Compare prompts on the same original Efficient models and inputs. Measure format validity
   and the source-bound semantic checks separately. Do not change acceptance at the same time.
2. Replay the same stored, verified first-stage observations under explicit acceptance profiles.
   This is a routing/acceptance experiment, not new model evidence or a future-stage replay.
3. Optionally run bounded focused refinement inside the existing Efficient stage. These are
   new answers from existing voters, not additional independent votes.

The historic Run 078 inputs cannot retroactively provide confirmed source structure.
Use the [readiness pilot](taxonomy-partial-readiness.md) separately when testing deterministic
savings. Pending Requirement, Objective and Technique rules stay pending; a model majority
or a new file format cannot qualify a rule or confirm a source.

## Explicit profile files

`--acceptance-profile` on `evaluation partial-cascade` selects a YAML profile. Its full content
and fingerprint are bound into the frozen run plan, effective configuration, acceptance,
resume and archive replay. Changing a profile requires a new output directory. Unknown keys,
coerced scalar types, unsupported versions and invented `qualified` status are rejected.

| File under `cfg/evaluation/partial-cascade/` | Experimental change |
| --- | --- |
| `statement-two-thirds-v1.yaml` | Exact two-thirds Statement-Primary support rather than the decimal 0.67 boundary |
| `role-evidence-v1.yaml` | Three-quarters Role-Presence support plus a conservative minority-evidence guard |
| `applicability-positive-v1.yaml` | Three-quarters positive gate; negative gate requires unanimous available votes |
| `efficient-evidence-v1.yaml` | The three acceptance candidates together, without new model calls |
| `efficient-focused-v1.yaml` | The combined candidate plus bounded same-voter refinement |

These are proposals for qualification, not generally safer or more accurate rules.
Existing minimum-voter requirements, accepted/review categories, source conflicts and
primary/set consistency checks still apply. A missing or invalid observation is not a
negative vote. Ties are not accepted. The completion profile is not reduced.

### Statement Function

The experimental threshold uses integer fractions: `2 / 3` meets a two-thirds threshold
but does not meet the legacy decimal `0.67`. An explicitly higher stage minimum or consensus
floor is preserved, and the final stage-local Statement resolver is not relaxed. Diagnostics
record the actual support numerator/denominator and required fraction. The same accepted
state is consumed by mandatory review and routing.

### Role Presence and minority evidence

The candidate replaces the presence-unanimity requirement with at least three-quarters
support (or a higher consensus majority floor). A proposed negative result is still protected
against contradictory relation evidence when **either**:

- a proposed actor occurs as a case-insensitive, word-bounded sequence in the local clause; or
- the same complete relation tuple has been independently proposed by at least two voters.

A single unanchored tuple remains visible but is no longer an unconditional veto. This is
only a conservative lexical/corroboration guard, **not** a proof that the relation is correct
or that the clause has no role semantics. Synonyms, translations, implicit actors and
paraphrases require a reviewed semantic test set. An accepted empty relation set alone does
not prove absence. No model is excluded and no original relation suggestion is deleted.

Evidence from earlier observations is retained for this guard, so re-questioning one voter
cannot erase an earlier literal-actor warning. Repeated attempts by one voter never provide
independent corroboration. Previously accepted values remain frozen; later contradictory
observations remain diagnostics, as in the baseline.

### Applicability gates

Three-quarters positive Presence support can open the existing detail policy. A negative
candidate remains open whenever an available positive vote disagrees. Unanimity still needs
the configured number of successful voters. This is a gate policy, **not** a final normative
Applicability classification. It may increase downstream work and unknowns.

There is no `clause_type != requirement` exclusion and no `technique -> false` rule. Pure
technique usability and normative applicability remain distinct; notes and mixed text are
not discarded. The final `D4 OR (D3 AND D1)` rule and Golden FP/FN limits are unchanged.

## Model-free profile comparison

Use the **complete** existing experiment directory or its ZIP, not a summary or audit JSON:

```bash
uv run standards-atlas evaluation partial-profile-compare \
  --experiment local/evaluation/taxonomy-efficient/slice-5/run-078-50-v2 \
  --profiles cfg/evaluation/partial-cascade/statement-two-thirds-v1.yaml,cfg/evaluation/partial-cascade/role-evidence-v1.yaml,cfg/evaluation/partial-cascade/applicability-positive-v1.yaml,cfg/evaluation/partial-cascade/efficient-evidence-v1.yaml \
  --output local/evaluation/taxonomy-efficient/slice-6/profile-compare-078
```

Substitute the actual directory of the executed source run. The output must be new and
separate from source/canonical data. The command verifies source artifacts and regenerates
requests before recomputing the original Efficient evidence under the baseline and each
profile. Original files and acceptances do not change. It writes
`partial-profile-comparison.json` and a mixed-consensus snapshot per variant.

Only the original first-stage observations are compared; old focused or later-stage answers
are not treated as independent first-stage evidence. Changing acceptance changes future
requests, so this report deliberately does not invent an end-to-end counterfactual. Passing a
focused profile here evaluates its acceptance rules only; `focused_inference_not_executed`
explicitly marks the unavailable new answers. Completion changes are **not** accuracy gains.

## Compare all Efficient models and Process sentinels

```bash
uv run standards-atlas evaluation partial-efficient-compare \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --run local/evaluation/qualification-run-078.zip \
  --prompts taxonomy-partial-v2,taxonomy-partial-v3-no-process-null,taxonomy-partial-v4 \
  --checks src/standards_atlas/resources/semantic/qualification/process-functions-sentinels-v1/checks.json \
  --limit 50 \
  --output local/evaluation/taxonomy-efficient/slice-6/efficient-prompts-078 \
  --execute
```

Without `--execute`, only plans are written and no gateway is initialized. With it, every
configured first-stage model processes the same frozen source selection for each prompt.
Intermediate, Final and the final Applicability detail policy are not run. The default
comparison has no acceptance profile, isolating the prompt change. An explicit profile can
be held constant across all variants for a later comparison.

The output contains `efficient-comparison.json`, independent per-prompt run directories,
per-model immutable response audits and source-bound readiness results when `--checks` is
provided. A new audit/readiness revision is written if repaired observations change; prior
results are retained. Repeating the identical configuration resumes compatible observations.
Source, prompt, manifest, profile or check changes require a new comparison output.

A fixed First-N selection is not representative of all clauses. Format validity, semantic
sentinels, required completion, optional attribute coverage and measured costs must be read
separately. No readiness result changes accepted model evidence or promotes the profile.

## Bounded refinement in a full candidate run

```bash
uv run standards-atlas evaluation partial-cascade \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --run local/evaluation/qualification-run-078.zip \
  --prompt taxonomy-partial-v4 \
  --acceptance-profile cfg/evaluation/partial-cascade/efficient-focused-v1.yaml \
  --limit 50 \
  --output local/evaluation/taxonomy-efficient/slice-6/focused-078 \
  --execute
```

Run this only as an explicit candidate; v4 remains unqualified until its semantic checks pass.
For a confirmed-source pilot, use `--dataset` instead of `--run` and optionally add
`--require-taxonomy-decisions`. The latter intentionally refuses legacy data without fixed
source decisions before starting a model. Normal runs preserve the full clause denominator.

After the first-stage base observations, the planner selects at most **one open group per
clause**, prioritizing clauses with fewer required blockers, then Statement, Role Presence,
Applicability and finally Knowledge Kind. Knowledge refinement is limited to actual open
`process`/`technique_or_measure` splits; the response schema still allows other valid
Knowledge categories or a justified null. Source conflicts are not model-resolved.

The shipped focused budget is:

| Limit | Value |
| --- | ---: |
| Distinct clauses | 12 |
| Physical focused requests | 24 |
| Existing Efficient voters per selected clause | At most 2 |
| Maximum requested output tokens per request | 384 |
| Total reserved maximum output tokens | 9,216 |

The budget accounts for physical attempts across resumes and retired stage revisions. It is
an **output-token allowance**, not a tokenizer-derived total-input/output or wall-time cap.
A focused request has one attempt, with truncation retries disabled. An already attempted
focused failure is retained rather than retried automatically on resume. Unused budget and
unresolved cases continue through the normal cascade. A zero budget is supported.

The same provider/model receives `taxonomy-focused-v1` and only its selected open group.
There is no extra adjudicator identity: the later response replaces that voter's open answer.
Accepted attributes stay frozen, omitted fields produce no votes, and a failed grouped answer
is not salvaged. The new prompt uses the existing full schema with Process independence and
normative Applicability boundaries; no candidate value is forcibly inserted.

`mixed-before-focus-report.json`, `focused-plan.json` and per-job original request/response/
attempt artifacts make this round replayable. Before archive adoption the reader regenerates
selection, constraints, request identities, budget and focused-stage acceptance. Extra
attempts, changed plans and incompatible profiles fail verification. Normal cascade costs
include focused work once and expose it as a separate subtotal. The cascade audit labels it
`same_voter_refinement`; retired work is never counted as additional voters.

## Source-bound semantic predicates

The readiness evaluator also accepts explicit equality predicates for current attributes:

```json
{
  "attribute_checks": {
    "role_semantics_present": {"equals": false},
    "primary_knowledge_kind": {"equals": "concept"}
  }
}
```

These predicates are added to a case in the existing source-bound check file, including its
source identity and content hash. Booleans and numbers are distinct, and set-valued fields
are compared order-independently. Missing, unrequested, invalid or unverified source evidence
remains unavailable. Independent diagnostic passes do not salvage a failed whole observation.
Checks must come from review; the command does not manufacture Golden labels or human approval.

Before release retain the agreed complete Applicability Golden corpus, fixed-presence and
end-to-end fresh repetitions, and separate reviewed Role/Knowledge/Process tests. No 80%
Efficient completion claim or semantic release follows from the unit tests or profile replay.

## Final qualification and activation

See [the final qualification campaign](taxonomy-partial-qualification.md) for pinned
cohorts, independent fresh repetitions, explicit full baselines and reviewed activation.
Candidate availability or a passing integration test alone never promotes a profile.
