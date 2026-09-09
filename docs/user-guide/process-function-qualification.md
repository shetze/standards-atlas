# Process functions in qualification and persisted CBox attributes

The qualification path now retains `process_functions` and `primary_process_function`
from structured responses through per-model votes, consensus, cascade snapshots, reports
and explicit canonical/AtlasData adoption. It uses the existing process vocabulary and
persistence contracts; no new canonical repository or public storage format is introduced.

## Availability is separate from the selected value

| Input evidence | Set interpretation | Primary interpretation |
|---|---|---|
| Both fields explicitly supplied | Observed selection, including an empty set | Observed label or explicit null |
| Set supplied, primary omitted | Observed selection | Not evaluated |
| Both fields omitted and then defaulted by normalization | Not evaluated | Not evaluated |
| Measured votes tie or lack sufficient valid participation | Unknown decision | Unknown decision |

New annotation generators persist `provided_fields` alongside their provenance. These are
keys actually supplied by the provider, not keys added to satisfy a newer task schema.
Adaptive interviews record only decisively answered dimensions. Skipped/unclear process
questions do not become empty selections. Missing process fields in a different selected
prompt do not fall back to observations from another prompt.

Repetitions are collapsed into at most one coherent vote per model. A tied repeat mode
abstains; repetition counts and stability remain inspectable. Missing fields, abstentions
and model failures never count as negative process votes.

## Independent primary and set decisions

The primary uses a strict majority of valid primary observations. Explicit null is a valid
answer; a tie is not a null decision. The set uses per-label strict majorities and the
configured consensus `label_threshold`. A majority primary label is retained in the set
when it also has majority set support. An empty set is accepted only with a majority of
explicit empty-set observations, not merely because no label passed a threshold.

The report retains primary support, per-label set support, valid participation, explicit
empty/null decisions, and **exact-set agreement separately**. Set confidence is the minimum
support of retained labels (or empty-set support); it is not the frequency of identical
whole-set answers. Primary disagreement does not discard a separately decided set.

These measures describe agreement, **not accuracy against a human golden corpus**. The
usual minimum-model quorum and consensus categories remain visible. Adoption accepts
usable majority decisions even when the overall clause needs review for another dimension.
Insufficient or conflicting decisions remain unknown. Replacing a set cannot leave a stale
primary outside that set; clearing such a primary is marked unknown, not a measured null.

## Existing manifests and optional escalation

No manifest change is needed to collect process fields already returned by its prompts.
`consensus.prompt_selection.process_function` defaults to the selected statement-function
prompt. It may explicitly name another prompt ID already declared and run by the matrix:

```yaml
consensus:
  prompt_selection:
    statement_function: applicability-presence
    process_function: applicability-presence
```

This fragment augments an existing manifest; it is not a complete matrix.

Additional process-driven escalation is **off by default**, preserving the existing
manifest's inference workload. To make process quality trigger later stages, extend each
applicable stage's `resolution` block, for example:

```yaml
resolution:
  minimum_successful_models: 3
  minimum_process_function_confidence: 0.6
  minimum_process_set_confidence: 0.6
  process_function_resolution_mode: cumulative
```

A stage-local `resolution` replaces the matrix default; a change only to the default does
not modify stages that already supply their own resolution. Alternatively the two flags
`escalate_on_process_function_disagreement` and `escalate_on_process_set_disagreement`
require unanimity when no corresponding confidence threshold is set.

Primary resolution can explicitly use `process_function_resolution_mode: stage_resolver`
with `process_function_resolver_min_confidence` (default 0.75). A stage resolver uses that
stage's actual votes and a one-model minimum; this is a policy choice, not independent
multi-model validation. Set resolution remains cumulative. Frozen primary and set snapshots
keep their own source stages and support denominators. A later incompatible combination is
reported as a conflict instead of silently unioning labels or claiming a new decision.

## Reports and compatibility

New consensus reports write schema **5.0**. Votes and clause results carry explicit process
availability, set/primary decisions, categories, support and participation. Analysis metrics,
cascade diagnostics, review tables and the golden proposal include the dimension. The
**golden proposal writes schema 4.0** and remains a proposal, not published gold.

Consensus schema **4.0** stays readable. Its normalized serialization is preserved to keep
existing policy selection fingerprints valid. In particular, reading an old Run 074 archive
must not add default process votes or break its Applicability selection hashes. New report
writers emit 5.0; the reader does not rewrite the old archive.

Canonical `EngineeringDocument` schema **9**, adoption contract **1.0**, and archive layout
**1.5** are unchanged. AtlasData enrichment companion schema **1.1** keeps the same process
values and decision provenance while reorganizing its readable persistence layout.

## Recomputing retained proposal runs without new inference

An old consensus alone cannot reconstruct process observations. When the original local
proposal directories still contain `evaluation.yaml` and `response.json`, the consensus
reader can recover field availability from the original **structured** response. Provider,
model, prompt, input hash, response hash, selected values and types must match the candidate.
Rationale text is never parsed as a substitute. Legacy aggregate interview outputs without
explicit availability are not reconstructed.

For a complete retained proposal run, use the existing recompute mode:

```bash
uv run standards-atlas evaluation qualification-matrix \
  --manifest manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml \
  --recompute
```

Recompute preserves candidates and rebuilds derived reports; it does not fill missing
proposal runs with new inference. Keep the current corpus, selection and matching proposal
directories. It fails when required candidates are missing. Do not combine it with `--fresh`,
`--no-reuse` or `--no-cache`. Missing structured process fields remain not evaluated.

A recomputed consensus has a **new identity**. An old Applicability policy/selection bound
to the previous consensus must not simply be copied beside it. Rebuild dependent policy
selection/report artifacts and create a coherent immutable analysis archive through the
existing qualification/policy workflow before adoption. The standard model-backed workflow
is separate from consensus-only recomputation and may need inference according to its mode.

## Adopt and persist

For a coherent new qualification archive, process functions are included in the default
five-dimension adoption. To preview only this dimension, use your new archive path:

```bash
uv run standards-atlas document adopt-qualification \
  --run local/evaluation/qualification-run-NEW.zip \
  --dimension process_functions \
  --workspace .atlas/data \
  --output local/review/process-adoption-preview.json
```

Replace `qualification-run-NEW.zip` with the actual archive. Add `--write` after inspecting
the preview. The archive must still include the complete policy/selection evidence even
when selecting only process functions. Then use the existing
[AtlasData export/import](atlasdata-enrichments.md) or explicit
[knowledge workflow](canonical-cbox.md). No new publication happens implicitly.

Run 074 remains a valid old input: its process dimension is **not evaluated**, while its
497 Applicability decisions remain 45 positive and 452 negative. The three unqualified
cases are untouched. This is legacy compatibility, not a new process-quality evaluation.

## Tests

`tests/integration/atlasdata/test_process_qualification_roundtrip.py` runs fresh deterministic
fake-gateway responses for three models, builds structured proposals and consensus, checks
an immutable archive, adopts, exports and restores the CBox. It covers positive labels,
explicit empty/null, absent fields, support, protected values and idempotent replay. It
performs no external inference and makes no claim about real-model classification accuracy.

Unit tests cover different prompts, repeat abstentions, raw-response recovery, independent
stage/resolver snapshots, conflicts, schema-4 hash preservation and human-review retention.
The existing opt-in Run 074 tests exercise the legacy archive against isolated source-matching
documents; no protected standards text is embedded in repository test fixtures.
