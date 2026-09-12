# Experimental partial semantic observations (Slice 4)

`evaluation partial-proposals` plans and optionally executes **only selected, still-open
semantic attributes**. This is a separate experimental task, not a replacement for the
production qualification matrix. It does not compute consensus, count production early
exits, adopt canonical values or publish `data/enrichments`.

The production task, its full-output schemas and the three Slice-3 comparison manifests
remain unchanged. The existing `annotations-propose` generator explicitly rejects the
new partial task rather than filling its omissions with full-answer defaults.

## Contract

Task `semantic-attribute-observation` **1.0.0**, prompt `taxonomy-partial-v1`, and frame
`taxonomy-grounded-v1` are independently identified. The task envelope allows exactly
nine current semantic attributes: the three statement/knowledge/process primary/set
pairs, `applicability_present`, `role_semantics_present`, and structured `role_relations`.
Optional `confidence` and `rationale` describe the requested response only.

Each request projects this envelope onto its open attributes and makes **all of those
attributes required**. Any unrequested semantic output is rejected. This is not the
old adaptive interview: there are no Applicability subtypes, scalar role answers or
compatibility fallback calls. Role objects retain `actor`, `relation_class`, and `target`;
`relation_class` stays open. Passive role semantics can be present with an empty relation
set. Applicability still concerns normative validity, not pure technique usability, and
has no carrier-clause-type gate.

A new `PartialRequestPlan` derives the diagnostic source plan again from the input, not
from cached semantic answers or golden labels. Only qualified, source-backed `fixed`
attributes are omitted. `hint`, `open`, and `conflict` remain questions. Today the rules
can fix a **confirmed term's primary definition function**; unreviewed objective and
technique rules remain hints. Unattributed historical clause types are not promoted to
confirmed facts. Incorporating accepted model decisions across cascade stages is part
of Slice 5, not an implicit read from persisted enrichment here.

A fixed primary does not determine its complete set. If the set is requested, its fixed
primary is supplied as a separately identified constraint, not repeated as a requested
answer or a model vote. The set must still be independently evaluated and returned.
There is no silent insertion of missing members. A real primary/set contradiction is
preserved as a failed grouped observation with raw evidence for later examination.

All open questions are bundled into **one request per clause and model**. There is no
unconditional request per dimension. When all selected attributes are fixed and no
additional work is selected, there are **zero requests**, including zero gateway/server
initializations. The default selection includes all nine attributes; choosing fewer
attributes is an explicit experiment, not a qualification completion claim.

## Model-free planning

Use an immutable qualification archive or directory:

```bash
uv run standards-atlas evaluation partial-proposals \
  --run local/evaluation/qualification-run-078.zip \
  --model 'hf.co/ibm-granite/granite-3.3-8b-instruct-GGUF:Q4_K_M' \
  --output local/evaluation/taxonomy-efficient/slice-4/run-078-granite \
  --limit 50
```

Without `--execute`, **no model or runtime configuration is accessed**. The model name
is still necessary because it belongs to the planned request identity. `--limit` is an
explicit first-N selection, not a count of pending cases and not stratified sampling.
The report retains both the original input count and the selected/accounted count.
Omit `--limit` to plan every selected source clause. Planning is not a new LLM baseline.

For a freshly built corpus carrying source provenance, replace `--run ...` with:

```bash
--dataset local/evaluation/taxonomy-efficient/slice-3/corpora/semantic-profile-classification/2.2.0/dataset.json
```

That path applies when the separate corpus was built using the command in the
[Slice-3 guide](taxonomy-grounded-qualification.md). `--run` and `--dataset` are mutually
exclusive. Archive selections and checksums are verified. Source dataset/corpus versions
are preserved in the experiment rather than pretending to be the new task version.
Expected answers and tags are stripped before preparation.

## Explicit execution and resume

Repeat the same command with **`--execute`** to execute pending questions. A matching
successful observation is reused; failed or interrupted cases are retried. Runtime
creation is lazy: an entirely reused or zero-question run does not contact a server.
RamaLama uses `--config cfg/llm.yaml`; the requested model is applied to both gateway and
server configuration. A mismatched already-running model is rejected by the existing
server manager, not silently relabeled. A server started by this command is stopped on
exit; an already matching server is left running. Codex can be selected with `--provider
codex` and uses the existing managed MCP lifecycle.

A focused experiment can select, for example:

```bash
--attributes primary_function,statement_functions,applicability_present
```

Supply that option in both planning and execution. Do not change it when resuming the
same output. `--attributes role_relations` asks for the structured extraction without
inventing an accompanying Presence observation. Historical scalar `role_relation_types`,
`applicability_functions`, and a new `usability` field are not supported outputs.

The default CLI generation budget is 512 tokens with one possible truncation repair at
1024 tokens. `--max-tokens`, `--truncation-retry-max-tokens`, `--temperature`, `--seed`,
`--retry-attempts`, and `--retry-timeouts` are explicit controls. Changing generation,
source context, task/prompt, rule profile or attribute selection requires a **new output
directory**. Existing inputs are never overwritten just to make stale proposals fit.
Each attempted request is archived separately. Retries do not add voters.

Identical requests can still use the configured provider cache, even in a new output
directory. A new output is **not a fresh inference claim**. For a fresh experiment, use a
new output and disable the RamaLama cache through the existing configuration, for example
`STANDARDS_ATLAS_LLM_CACHE_DIRECTORY=''` before the command. This is not a substitute for
the later repeated end-to-end qualification.

## Artifacts and interpretation

The output directory is immutable in identity, but resumable in execution:

```text
partial-run-plan.json          selection, configuration and request fingerprints
partial-run-report.json        current invocation's accounting and measured costs
cases/<identity-hash>/
  partial-request-plan.json    source plan, selected/open/fixed attributes
  eligibility.json            explicit task eligibility; ineligible is not successful
  request.json                only when a model question exists
  response.json               latest structured response, when one was returned
  partial-observation.json    one current logical observation, not a full annotation
  executions/execution-*/
    attempt-001.json           exact request and response/error for each actual attempt
    ...
    request-timing.json        costs of this execution, including failed attempts
    partial-observation.json  historical execution outcome, when completed
```

Independent internal schema families (`partial-request-plan`,
`partial-semantic-observation`, `partial-proposal-run`) start at **1.0**. They do not
change EngineeringDocument, consensus, or AtlasData schemas.

For every current task attribute, `partial-observation.json` records:

| State | Meaning | Model evidence |
|---|---|---|
| `evaluated` | Requested and successfully validated | Only the explicitly returned value |
| `not_requested` | Fixed or outside the explicit selection | None, not `false` or `[]` |
| `failed` | Requested group failed inference/schema/consistency checks | None; raw attempt retained |

`values` contains only a valid group's actual fields, and `provided_fields` records the
structured fields returned by the gateway. Raw invalid gateway output remains in attempt
files. No missing member or companion attribute is normalized into existence. A requested
`null` primary or explicitly empty set is a real observation, not a missing answer; that
still does **not** mean production acceptance. A malformed group fails as a group; there is
no silent salvage of some fields followed by synthesized defaults for the rest.

The report separates planned groups, actual gateway calls, new/reused logical observations,
and per-clause failures. Request timing covers **this invocation only**; older execution
records remain available and must be included when comparing total experiment cost.
Returned cached provider durations remain historical rather than fresh inference time.
`production_early_exit_count` is deliberately unavailable. Changing the denominator or
asking only an easy field cannot demonstrate the 80% Efficient target.

There is no `evaluation.yaml` and no automatic collector/adoption bridge. Full-output
proposals are not imported into this new context experiment. Sparse `model_evidence()`
contains no entry for unrequested or failed attributes. This preserves the boundary for
Slice 5's mixed-evidence consensus, routing and provenance integration.

The output cannot be a source run or public/canonical document directory. Atomic writes
and a single-writer lock protect resume. Interrupted attempts remain in their execution
directories. After an external process kill, remove a stale `.partial-run.lock` only after
verifying that no writer is still using the output. Corrupted successful response checksums,
mismatched plans or unsupported schema versions fail visibly rather than being silently
reused. Per-clause inference failures are collected and do not stop later clauses.
