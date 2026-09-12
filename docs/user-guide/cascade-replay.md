# Diagnose a qualification cascade without model inference

`evaluation cascade-replay` writes a separate audit report from existing qualification
artifacts. It never starts a model server, generates proposals, writes public enrichments,
or overwrites the original run. It is not a fresh qualification, an Applicability-policy
replay, or evidence that new prompts achieve the same accuracy.

## Corrected routing from an archived run

```bash
uv run standards-atlas evaluation cascade-replay \
  --run local/evaluation/qualification-run-078.zip \
  --mode routing \
  --output local/evaluation/cascade-replay-078-routing
```

The output directory must not exist and must be outside the input run directory. The
command creates `cascade-replay.json` and `cascade-replay.md`. Use a new output directory
for each comparison. `routing` is the default mode.

The selection denominator stays fixed. Every selected clause is accounted for, including
clauses that have no consensus record. Missing initial, cumulative or stage-local evidence
is unresolved, not a negative semantic answer or a successful early exit. The stage report
separates completed clauses, unresolved clauses and missing consensus observations.

A corrected route can require a later-stage observation that was never produced. These
cases appear under `requires_inference`. The routing mode uses the archived stage
consensus; it cannot reconstruct changed cumulative votes and does not claim to be a
complete counterfactual run. A clause may have archived final consensus but still lack the
stage-local observation required to replay a particular decision.

## Three modes

| Mode | Evidence and operation |
| --- | --- |
| `historical` | Inspect the original admitted selections and exit reasons; expose missing records without replacing historical decisions with new ones. |
| `routing` | Apply the corrected production routing and dimension-capture functions to existing stage consensus. Do not recompute the model consensus. |
| `proposals` | Validate local requests and proposals against the immutable selection and original configuration, then recompute stage and final consensus with the existing service. |

Original stage metadata remains under `historically_recorded`. Historical counters are not
silently relabelled as corrected counters. Source fingerprints, stage reasons and resolution
captures are included in the JSON report. Missing historical times remain unknown.

Historical inspection:

```bash
uv run standards-atlas evaluation cascade-replay \
  --run local/evaluation/qualification-run-078.zip \
  --mode historical \
  --output local/evaluation/cascade-replay-078-historical
```

## Recompute from local proposals

The ZIP need not contain every original proposal. Supply the same `--runs-output` root
used to create the run; it is the parent of `qualification-runs`, not an individual model
case directory. The following example uses the CLI default root:

```bash
uv run standards-atlas evaluation cascade-replay \
  --run local/evaluation/qualification-run-078.zip \
  --mode proposals \
  --runs-output .atlas/data/evaluation/runs \
  --output local/evaluation/cascade-replay-078-proposals
```

Use `--resources` when the original semantic resources are not the installed defaults.
A request is usable only when the reconstructed original request matches `request.json`,
including task, prompt, input, frame and generation settings. A changed or absent request
is `requires_inference`; it is never silently regenerated. Proposal clause, document and
content identities must also match. An existing recorded failure is preserved as a failure,
not converted to a negative vote.

This mode additionally writes recomputed reports under `consensus/` in the separate output.
It does not re-run the Applicability detail policy, produce fresh model qualification/F1
metrics, adopt the results into canonical data, or publish an enrichment. The run can still
be incomplete when the corrected route requires proposals that do not exist locally.

## Input and schema checks

A ZIP contains its archived manifest. A run directory is also supported when it contains
its immutable selection and corpus/dataset snapshots, stage reports and provenance. Supply
`--manifest` if that directory has no `configuration/qualification-manifest.yaml`. An explicit
manifest must match an archived configuration when one is present; this command is not a
manifest-override experiment.

Consumed archive members are checked against their manifest SHA-256 values. Selection
fingerprints, counts, unique identities, document coordinates, corpus identity and effective
stage settings are checked before replay. Ambiguous artifacts, unsafe paths and unsupported
schemas fail clearly. Consumed source artifacts are read-only and fingerprinted.

Supported contracts for this slice are selection schema `1.2`, cascade-provenance schemas
`1.5` and `1.6`, and the existing bounded consensus schemas. New provenance uses `1.6`;
the replay report and per-case request timing use `1.0`. Qualification-matrix reports use
`1.1` with bounded reading of `1.0`. Archive metadata and public enrichment schemas are
unchanged. These changes do not alter any task, ontology, prompt or acceptance threshold.

## Cost measurements in new qualification runs

Each actually processed proposal case stores `request-timing.json`, including requests
that returned invalid content, retry calls, and gateway exceptions. It separates:

- measured provider inference for fresh returned responses from historical cached durations;
- all gateway calls and failed calls, with measured gateway wall time;
- observation wall time and complete stage wall time, which also includes model startup.

The matrix mean is the sum of measured inference durations divided by the number of
measured requests. Unequal batches are pooled using request counts, not by averaging their
batch totals. A gateway exception without a provider duration has known wall time but
unknown provider inference time. Failure/retry provider time is not estimated.

A response may have a valid duration of zero. Missing, negative or non-finite durations are
unknown. A resumed/recomputed observation can use recorded historical request durations;
it does not claim fresh work. A fully reused execution records zero new gateway calls.
`request_timing_complete` and `timing_observation_count` expose partial timing coverage.
Do not add historical reference measurements to fresh execution costs.

Old automatically recorded matrix batch sums lack the required denominator and are not
used as per-request latency. Where individual old response files have trustworthy timing,
it can be reconstructed. Old adaptive-interview aggregates and old failures without
per-call measurements remain unknown. Explicit legacy user-declared means remain readable
and labelled separately, but are not silently mixed with measured request averages.
