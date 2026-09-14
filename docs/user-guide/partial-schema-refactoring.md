# Partial schema refactoring (R1)

R1 removes support for obsolete intermediate formats in three experimental partial
families. It is not a migration feature and does not alter semantic acceptance rules.

| Family | Read and write | Artifact |
| --- | --- | --- |
| `partial-request-plan` | 1.1 only | `cases/<id>/partial-request-plan.json` |
| `partial-semantic-observation` | 1.1 only | `cases/<id>/partial-observation.json`, execution/revalidation copies |
| `partial-cascade-report` | 1.1 only | `partial-cascade-report.json` |

The outer `partial-proposal-run` and `partial-cascade-run` families remain at **1.0**.
A version number alone is not a reason to replace an artifact: its **schema family**
determines the contract. Other families are reserved for the subsequent refactoring slices.

## Prompt capability is not a serialization version

All configured partial prompts, from `taxonomy-partial-v1` through the later variants
and `taxonomy-focused-v1`, use the same current request-plan and observation formats.
Their prompt contents, task resources and acceptance thresholds are unchanged.

`taxonomy-partial-v1` remains usable for point requests but cannot carry previously
accepted attributes. Cascade execution still requires a constraint-capable prompt.
Neither adopting schema 1.1 nor renaming an artifact grants a prompt new capabilities.

The request plan always serializes `accepted_attributes` and `accepted_state_sha256`,
including the explicit empty/absent values `{}` and `null`. The old serializer that
omitted those fields to preserve a 1.0 identity has been removed. Observations declare
their own family's version; they do not copy it from the plan. Both version markers
are required on persisted input, including nested plans.

## Existing runs and identities

Current-format runs remain resumable when source text, structure, task, prompt,
generation settings, question selection and accepting-state fingerprint still match.
Changing the serialized content changes the plan/request identity; no alias allows a
saved response to be reused under a changed fingerprint.

An obsolete or unversioned artifact is an error, not a deprecation warning. In particular:

- Resume rejects 1.0 request plans/observations, including a 1.0 plan inside a 1.1 observation.
- Offline response revalidation does not upgrade schemas or rebind saved responses.
- A saved 1.0 cascade report cannot be silently replaced by a new invocation, even for
  planning only. A malformed execution flag, missing run mode or changed effective
  configuration also blocks resume before inference or report replacement.
- Direct readers, cascade replay, diagnostics, focused-budget accounting and review-history
  observations use the same current model contracts. Archive replay does not bypass them.

Keep obsolete files unchanged as historical evidence. Use a **new output directory** to
regenerate affected plans and observations from their original source/configuration.
Do not hand-edit version markers, copy old response JSON into a new run or delete evidence
as a side effect of applying this patch. A full model execution is needed only when new
model evidence is actually required; planning itself remains model-free.

No corpus labels, HITL decisions or historical archives are rewritten by R1. No generic
migration utility is provided.

## Execution and observation semantics

A current cascade report must explicitly record `executed`, `run_mode` and
`effective_configuration`. Replay always checks the effective configuration against the
frozen plan/resources and recomputes presentation metrics from verified decisions.

For a planning-only run, `completion_rate` remains `null`, `benchmark_eligible` remains
`false` and `measurement_status` is `not_executed`. A planned run is not a measured 0%.
An executed or resumed run is still not evidence of fresh repetition qualification.

`evaluated`, `not_requested` and `failed` remain distinct. Already accepted or structurally
fixed values do not become additional model votes. Explicit `false`, `null` and empty
sets are preserved when genuinely observed, but are never synthesized from missing values.

## Verification

The dedicated regression suite covers current writer/reader roundtrips, all supported
prompt variants, carry-state binding, missing/obsolete/nested version rejection, writer
policy drift and refusal to overwrite obsolete evidence:

```bash
uv run pytest tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py
```

It complements the existing partial proposal, response identity, carry, cascade, audit,
comparison and mixed-consensus tests. R1 deliberately does not suppress warnings from
other schema families; those belong to R2/R3 and the final project-wide R4 guard.

See also [partial observations](partial-semantic-observations.md),
[cascade readiness](taxonomy-partial-readiness.md) and
[the schema inventory](../reference/schema-contracts.md).
