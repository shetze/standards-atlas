# Effective CBox and knowledge workflows

The CBox is a read-only projection of the accepted `EngineeringDocument`, not a second
knowledge repository. Corpus construction, Prompt Workbench and `document cbox-report`
use the same projection. Neither old qualification reports nor Golden labels are read
by these consumers. Use [knowledge adoption](knowledge-adoption.md) to accept a result,
and [AtlasData enrichments](atlasdata-enrichments.md) to persist or restore it.

## Inspect the effective post-policy or post-import state

```bash
uv run standards-atlas document cbox-report \
  --workspace .atlas/data \
  --document ISO26262-11 \
  --knowledge-domain functional-safety \
  --output local/review/ISO26262-11-cbox.json
```

Repeat `--document` or `--clause` to select several physical documents or clause IDs.
Without document selection the report includes every canonical document in the workspace.
Unknown selections fail rather than silently falling back to all documents. `--available-only`
explicitly permits missing *document* selections and reports the resulting document set.

The versioned local report (`cbox-report`, schema `1.0`) contains each clause's accepted
canonical context, attribute sources, framed values, rendered text and fingerprints.
The nested `cbox-enrichments` contract is also `1.0`. EngineeringDocument schema remains
`9`; AtlasData companion schema remains `1.0`.

Attributewise availability is distinct from value:

| State | Interpretation |
|---|---|
| `known`, `generated` | A selected generated value, including explicit `false` or an empty set. |
| `known`, `confirmed` | The value has an explicit confirmation and its authority is recorded. |
| `known`, `unattributed` | An existing non-default/protected value without invented authority. |
| `unknown`, `generated` | An assessment exists but did not establish a value. |
| `not_evaluated` | There is no assessment; a Boolean model default is not a negative answer. |
| `partial` | Only descendants of a context object are attributed; the entire object is not promoted. |

Only `known` semantic attributes are exposed as hints. A primary label is not inferred from
set order, and a presence-only result remains useful without a detail function. A generated
hint is not automatically a curated fact or a hard governance-selection rule. The existing
attribute-level merge protects confirmed values before this projection is constructed.

The report is **private/local** and can include protected contextual evidence and derivation
metadata. It is not the public AtlasData companion. Keep it under `local/` or an appropriate
private workspace; the command rejects the repository's public data/manifest directories and
canonical/evidence stores as report destinations. It does not run models, modify canonical
documents or publish anything. An identical report is not rewritten.

A full canonical fingerprint includes content and available structural/attribute evidence;
a framed fingerprint includes selected facts but not rendered prose. A fresh public-only
import does **not** reconstruct protected source content or necessarily the private source
heading. Therefore full-context hashes can legitimately differ after such an import even
when every supported enrichment and its provenance has roundtripped exactly. Restore or
rehydrate local source evidence before comparing complete source-bearing contexts.

## Versioned frames and qualification isolation

`effective-context-v1` is the default report frame and is available in Prompt Workbench. It
shows accepted semantic hints and compact origin/support information as well as structural,
subject and routing context. Raw evidence and rationale remain in the local canonical audit
view, not in the compact origin hints rendered for prompts.

The previous `full-context-v1`, `applicability-minimal-v1` and
`applicability-isolated-v1` keep their existing field-selection policies. Additional explicit
frames are `semantic-isolated-v1`, `role-isolated-v1`, `routing-isolated-v1` and
`subject-isolated-v1`. The last two hide their respective contextual outputs. The renderer
is independently versioned (`2`); it does not decide attribute values or authority.

Qualification imposes the additional **`qualification-targets-v1`** selection boundary,
even if a manifest selects `effective-context-v1`: all stored semantic labels and their
provenance are removed from the prompt. Routing/subject tasks additionally omit their own
contextual results. Identity and genuinely selected structural information remain usable.
The stored semantic labels are not repackaged as `structural_roles`. This also prevents
adaptive interviews from choosing their questions from the previous semantic answer.

Selection applies consistently to `context_text`, `context_json`, `metadata`,
`structural_context` and direct heading variables. Arbitrary raw-context placeholders cannot
bypass it. Full raw context can remain in the **local request metadata** for auditing, not
in the model's system/user messages. Golden expectations are never template variables.

Prompt Workbench deliberately allows explicit downstream experiments using the effective
frame. Choose an isolated frame for an isolated experiment; its alternate metadata and
heading variables obey that frame too. Workbench results are not qualification evidence
merely because the same projection is visible there.

## Explicit model-free knowledge workflow

Inspect already accepted data without adoption, restoration or publication:

```bash
uv run standards-atlas workflow run \
  --task knowledge \
  --manifests manifests/standards.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

This runs only the CBox report. The workspace is the existing workflow workspace
`.atlas/data`. The physical document selection is resolved through the catalog/AtlasData
bindings, never a synthetic family document. Reports are stored under
`local/review/knowledge-workflow/<selection-hash>/` and their locations appear in the plan.
Missing documents/companions are explicitly reported as skipped; an empty selection never
falls back to unrelated documents.

To accept a run, publish selected canonical attributes and re-read the result:

```bash
uv run standards-atlas workflow plan \
  --task knowledge \
  --manifests manifests/standards.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety \
  --adopt-run local/evaluation/qualification-run-074.zip \
  --publish-enrichments \
  --strict-evidence
```

Use `workflow run` with the same arguments to execute the displayed plan. The sequence is
**adopt → export → reimport → CBox report**. `--restore-enrichments` additionally places a
restore before adoption, allowing existing accepted attributes to be recovered first.
The source archive must live outside disposable `.atlas/work`. Existing canonical source
content matching the adopted run is still required; a public skeleton alone cannot meet
adoption's source-content checks.

Every mutating step is explicit and uses the existing Slice 1/2 services with `--write`.
Each command performs its own source checks, merge and conflict handling. A public write is
possible only with `--publish-enrichments`, which is rejected for ordinary document and
qualification tasks. These commands do not make any LLM calls. The reimport runs through
the persisted files in another CLI invocation, not through an in-memory export result.
This is not an atomic multi-command transaction: a later failure does not roll back a
successful earlier adoption or export. Idempotent reruns revalidate the current inputs.
Do not execute overlapping writers concurrently.

Restore persisted attributes and inspect them without adopting or publishing:

```bash
uv run standards-atlas workflow run \
  --task knowledge \
  --manifests manifests/standards.yaml \
  --family ISO26262 \
  --knowledge-domain functional-safety \
  --restore-enrichments \
  --strict-evidence
```

The private evidence store is `.atlas/data/knowledge-evidence`. It is persistent, not a
cache. Without `--strict-evidence`, the existing importer defers contextual values needing
missing evidence instead of inventing empty conditions. The transfer report identifies
those `deferred` attributes; the CBox report shows what is actually available afterward.
For alternate workspaces/evidence locations or per-clause exports use the standalone
Slice 1/2 commands, not the default-workspace workflow wrapper.

## Opt-in restoration in document/qualification workflows

Add `--restore-enrichments` to a normal `documents` or `qualification` workflow. Restoration
is inserted **after taxonomy, before context enrichment and downstream corpus/export use**.
A post-context (or post-taxonomy) CBox report records the resulting canonical values.
`--strict-evidence` is optional and requires restoration. Neither option publishes data.
The default workflows still do not import companions implicitly.

For example:

```bash
uv run standards-atlas workflow plan \
  --task qualification \
  --manifests manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety \
  --restore-enrichments
```

This is still a **qualification** workflow, so new or changed model inputs can run inference.
Use the knowledge task for a strictly model-free restoration/report path. Existing source
and alignment review gates remain in effect. The final applicability decision is visible
in the effective CBox only after explicit adoption; merely running a qualification does
not accept its report as canonical knowledge.

## Reuse and invalidation

Proposal reuse no longer means only that `evaluation.yaml` exists. The persisted request
must match `qualification-input-v1`: source text/hash, task/profile/ontology contracts,
model/provider and generation settings, prompt template/schema/version, selected facts,
frame identity and isolation version. Changed actual inputs regenerate a proposal;
unchanged hidden labels do not. Old request files without the fingerprint are revalidated
once. A failed replacement cannot leave its previous success available for reuse.

A change to renderer prose alone does not invalidate a semantically identical proposal.
Requests and local audit metadata retain the originally executed prompt when a proposal
is reused; a new CBox report displays the current rendering. This is a semantic-input
reuse contract, not a claim that two differently rendered prompts were freshly tested.
To measure a renderer change experimentally, explicitly disable proposal reuse/run fresh.
The ordinary low-level LLM response cache remains keyed to the actual request.

Context routing records its input fingerprint in generated decision provenance. Matching
known routing can be reused after a restart/restore without gateway calls. Changed source,
subject evidence, prompt/schema or model configuration requires a fresh contextual result;
explicitly confirmed context remains protected and does not trigger an unnecessary call.
Deterministic subject identification can still be recomputed without a model.

Workflow corpus, context-enrichment and matrix checkpoints additionally track their live
inputs instead of just output existence. Relevant canonical data, contextual configuration,
prompt and ontology resources invalidate stale checkpoints. Context changes in another
document do not create a self-invalidating repository-wide loop. Renderer code is not a
classification input. Knowledge transfer/report stages always revalidate and then rely on
idempotent services, never on an old marker authorizing a public write.

Existing fixed qualification selections remain protected. If changed corpus inputs no
longer match a fixed run, the matrix raises its existing selection error; deliberate
replacement/new qualification is required. No source or Golden corpus is silently remapped.

## Regression commands

```bash
uv run pytest -q tests/unit/application/semantic_qualification/test_cbox_input_contract.py \
  tests/unit/application/workflow/test_knowledge_workflow.py \
  tests/integration/atlasdata/test_knowledge_roundtrip.py
STANDARDS_ATLAS_RUN074_ARCHIVE=local/evaluation/qualification-run-074.zip \
  uv run pytest -q -s tests/integration/knowledge/test_atlasdata_run074.py
```

The optional archive test runs against isolated physical AtlasData skeletons and local
archive-derived evidence, not the user's live workspace. It checks all 497 accepted
attribute projections after persistence/restoration. Process-function qualification and
further model-quality work remain separate; no missing classification is fabricated.
