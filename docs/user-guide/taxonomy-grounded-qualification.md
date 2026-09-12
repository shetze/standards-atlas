# Taxonomy-grounded qualification inputs (Slice 3)

`taxonomy-grounded-v1` is an **opt-in CBox frame**, paired with a new full-output prompt
of the same name. It supplies source structure to the existing multidimensional
classification task. It does not activate the diagnostic `ClauseDecisionPlan`, change
production acceptance rules, skip model calls or enable partial responses.

## What the frame exposes

The frame reads the `source_structure` contract introduced in Slice 2. It selects only
local heading, source clause type, canonical section, annex status, node kind,
document-family categories and explicit section labels/roles with valid text offsets.
Document categories must identify a `document.*` taxonomy; category and version are
preserved. Domain/semantic namespaces and unattributed bare category strings are not
silently reinterpreted as document taxonomy categories.

Up to four actual enclosing levels are visible, nearest first. Each parent keeps its
real distance and reference. Missing immediate-parent evidence does not turn a more
distant ancestor into the immediate parent. The whole source context remains in the
local request audit; the parent limit applies only to the model-facing projection.

The origin of each selected field is visible (`confirmed`, `deterministic`,
`source_extraction` or `unattributed`). Confirmation applies to the **source field**, not
to a semantic answer or an extra vote. Historical datasets without the new contract
remain readable as `legacy-context`, with all source observations unattributed.
The explicit reader accepts legacy `title` only when `heading` is absent.

Persisted semantic answers, expected/golden labels, diagnostic decision candidates,
interpreted routing, primary-subject context, reference-routing results, evidence
prose, generator names and authority identities are not model input. An explicitly
excluded/unavailable source field cannot fall back to its interpreted canonical copy.
The strict source contract rejects malformed or mismatched source identities rather
than inventing a fallback. Text and content hash are checked when building requests.

Section markers are ranges in the complete clause text. Invalid or out-of-range markers
are omitted, but **no clause text is removed**, including notes and unmarked content.
Context-only library calls without text omit unvalidated segment ranges; qualification,
workbench and CBox-report callers supply the full text and hash.

## Prompt and output contract

The new prompt distinguishes statement function from knowledge kind; an `Aim` within
a technique does not automatically make the entire clause an objective, and technique
steps do not automatically make its primary knowledge kind a lifecycle process.

Applicability concerns the validity of normative requirements/clauses. Pure technical
usability, an ordinary conditional obligation, a reference or an inherited scope alone
does not establish local explicit Applicability. There is no carrier-type gate: a note
inside a technique entry can still explicitly include or exclude requirements.

The output schema is **byte-identical to `structure-aware-v10`**, compatible with task
`semantic-profile-classification` **2.5.0**. All eleven required fields remain required,
including full label sets, primaries, applicability presence and structured role
relations. No new Usability field or public `applicability_functions` field is added.
The existing gateway, generation settings, retries, cascade resolution thresholds,
legacy production priors and `D4 OR (D3 AND D1)` detail policy are unchanged.

## Controlled comparison

Three manifests provide distinct matrix/run identities:

| Variant | Manifest suffix after `multidimensional-semantic-qualification-v7-` | Prompt | Frame |
|---|---|---|---|
| Control | `taxonomy-control-v1.yaml` | `structure-aware-v10` | `applicability-isolated-v1` |
| Context only | `taxonomy-context-only-v1.yaml` | `structure-aware-v10` | `taxonomy-grounded-v1` |
| Candidate | `taxonomy-grounded-v1.yaml` | `taxonomy-grounded-v1` | `taxonomy-grounded-v1` |

All three preserve the v6 models, stage composition, seeds, token limits, repetitions,
consensus/review thresholds and Applicability policy. The prompt candidate identifier
remains `applicability-presence` in each manifest so dimension bindings do not change.
The existing v6 manifest and default workflow are not replaced.

Use **one unchanged dataset/corpus pair** for all arms. A context-only/control comparison
isolates the new frame; candidate/context-only isolates the new prompt wording.
Later-stage samples can differ because the unchanged routing responds to different
votes. Compare Efficient on the identical first-stage selection, and total cascade
costs separately. Do not pool votes from these arms into a single consensus.

A small candidate run on the existing corpus can use:

```bash
uv run standards-atlas evaluation qualification-matrix \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --corpus-root .atlas/data/evaluation/corpora \
  --output local/evaluation/taxonomy-efficient/slice-3/qualification \
  --runs-output local/evaluation/taxonomy-efficient/slice-3/runs \
  --metrics-output local/evaluation/taxonomy-efficient/slice-3/metrics \
  --archive-output local/evaluation/taxonomy-efficient/slice-3/archives \
  --limit 50 \
  --fresh
```

Run the same command with the other two manifests without rebuilding the corpus in
between. Matrix IDs keep their artifacts separate. The direct evaluation command does
not adopt the resulting decisions into canonical documents or export enrichments.
Consensus review files use the existing manifest-owned review root and a distinct
matrix subdirectory. The unchanged optional review imports and local Applicability
golden-corpus path still need the same local prerequisites as v6.

`--fresh` forces new observations for a meaningful input comparison. A routing replay
cannot simulate model responses to the new context. `--limit 50` selects the existing
dataset's first 50 cases; it is a smoke test, not a stratified study or a guarantee that
all 116 published Applicability golden cases are included. No full LLM run is needed to
install Slice 3 or continue implementing Slices 4–5.

To build a **separate** new corpus with the source provenance (optional), first run:

```bash
uv run standards-atlas evaluation corpus-build \
  --task semantic-profile-classification \
  --version 2.2.0 \
  --corpus-id semantic-profile-v1 \
  --workspace .atlas/data \
  --output local/evaluation/taxonomy-efficient/slice-3/corpora \
  --count 100 \
  --strategy representative_stratified \
  --seed 20260912 \
  --source-only-context
```

Point **all three** matrix runs at that `--corpus-root`; do not change it between arms.
Keep the published Golden set and reviewed boundary cases in the later formal study.
Inspect selection/dataset fingerprints in the reports before interpreting comparisons.
The three required fresh fixed-presence and end-to-end Applicability repetitions remain
a qualification requirement, not evidence supplied by these model-free tests.

## Workbench, auditing and reuse

The Prompt Workbench lists `taxonomy-grounded-v1` as both a prompt and a context option.
Choose both for the candidate, or the v10 prompt with the new frame for the context-only
arm. Workbench template variables obey the same source boundary: an excluded heading
cannot leak through `{heading}` or `{metadata}`. CBox inspection can select the new frame
through its existing `--frame` option. No separate model endpoint or service is added.

Request fingerprints include the selected structural values, visible origin, frame,
prompt/task/output contract and generation configuration. Changes to visible source
structure invalidate proposal reuse; hidden semantic answers and renderer-only prose
changes do not. Full source/provenance data remain in the local `clause_context` audit,
not in the prompt. Existing frames keep their exact model-visible values and input
fingerprints. The renderer version advances to 3 to identify the added rendering path;
legacy prose is unchanged.

Tests cover field snapshots, source/content validation, excluded fields, manipulated
semantic/golden values, stable fingerprints, complete notes/text, full-output gateway
execution and workbench/report consistency. They establish input-contract correctness,
**not improved semantic accuracy or the 80% Efficient target**. Prompt length and actual
model cost must be measured alongside decisions in the empirical comparison.
