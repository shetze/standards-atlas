# Evaluation and qualification

The evaluation subsystem separates datasets, proposal runs, human review, metrics and published evidence. Generated model output is never automatically equivalent to a gold standard.

## Build a representative corpus

```bash
uv run standards-atlas evaluation corpus-build \
  --task semantic-profile-classification \
  --version 2.1.0 \
  --corpus-id semantic-profile-v1 \
  --knowledge-domain functional-safety \
  --count 500 \
  --strategy representative_stratified \
  --seed 20260804
```

The canonical multidimensional task is `semantic-profile-classification`. It composes the
independently versioned statement-function, knowledge-kind, process-function, applicability,
and role-relation ontologies used by the current qualification matrix.
`statement-function-classification` 2.x remains a compatibility alias for existing scripts and
artifacts; new qualification work should use the canonical task name.

The task metadata and central eligibility policy exclude `table_dominant` clauses by default.
The corpus manifest records the affected references, counts, content profiles, exclusion
reason, and the alternative task `structured-table-interpretation`.

`--include-table-dominant` exists for diagnostic or future table-specific tasks, but it
should not be used to enlarge a statement-function corpus. A flattened table is not a
single linguistic statement and would distort both labels and metrics.

Legacy task and corpus identifiers may remain in existing data. New classification work
should use the multi-dimensional semantic profile and domain-specific taxonomies.

## Clause and table task boundaries

Statement-function classification accepts clause artefacts and evaluates narrative
statement force. Table-dominant clauses are routed away from that task. Text-dominant
clauses with a small embedded table remain eligible, but prompts explicitly instruct the
model not to copy table-derived recommendations, responsibilities, applicability, or
traceability relations onto the surrounding clause.

The implemented table projection already provides addressable `KnowledgeTable` and
`KnowledgeRecord` artefacts. A separate evaluation task is planned for qualifying table
schema recognition, row extraction, relation extraction, reference resolution, and
IEC 61508 recommendation interpretation. Until that task exists, the deterministic
projection and its regression tests are the qualification boundary. See the
[structured table corpus roadmap](../roadmap/structured-table-corpora.md).

Proposal generation re-evaluates eligibility, so older or manually assembled corpora
cannot silently bypass the policy. Ineligible items are recorded in `eligibility.json`
rather than being treated as model abstentions or failed predictions.

## Qualification workflow ownership

The unified `workflow run --task qualification` plan reuses deterministic document preparation and
structural taxonomy, then explicitly runs the LLM-backed multidimensional semantic-profile
classification before corpus construction. This semantic stage is intentionally absent from
`--task documents`. Qualification keeps Markdown reference publication but does not execute
Doorstop export or Doorstop hierarchy publication.

`--limit N` limits the qualification matrix and semantic-extraction qualification sample. It does
not limit semantic-profile classification, because persisted EngineeringDocuments must never
contain a qualification-specific partial semantic profile. `--fresh` controls qualification model
reuse/cache behavior rather than changing this document-wide semantic boundary.

## Execute a qualification matrix

```bash
uv run standards-atlas evaluation qualification-matrix   --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml   --output .atlas/data/evaluation/qualification
```

Useful execution modes include:

- default/resume: retain completed candidate runs and continue missing work;
- `--overwrite`: replace the selected matrix output;
- `--recompute`: recompute metrics from persisted predictions where supported;
- `--limit N`: run a small diagnostic sample before committing resources.

The manifest controls models, providers, prompts, repetitions, runtime configuration, review imports and output locations. Per-model repetition overrides can prevent expensive remote providers from inheriting local-model repetition counts.

## Interpret evidence

Reliability rates are ratios in the range `0..1`; raw counts are reported separately. Compare semantic quality together with response validity, runtime, failure rate and resource cost. A Pareto result can legitimately be empty when no candidate satisfies required constraints.

## Human review and publication

Consensus proposals can help prioritize review but can bias reviewers. Keep proposals, reviewer decisions and published gold data as distinct artifacts. Published reviewed annotations take precedence over local proposals.

See [Annotation review](semantic-annotation-review.md) and [Testing and qualification](../development/testing-and-qualification.md).

## Regenerating runs for the knowledge ontology

The version 2.0.0 output contract now requires `knowledge_kinds` and
`primary_knowledge_kind`. Delete or overwrite proposal runs generated with the older
schema before rebuilding the qualification matrix. Use `--overwrite` for a complete
rerun. Review disputed IEC 61508-7 clauses first: `description` or `recommendation`
describes statement force, while `technique`, `measure`, or `method` captures the
engineering knowledge represented.


## Stage-specific prompt selection

Cascade stages may restrict the globally declared prompt catalog with a `prompts` list.
Omitting the list preserves the previous behaviour and executes every declared prompt for
every model in the stage.

```yaml
execution:
  mode: cascade
  stages:
    - id: efficient-local
      models: [granite-8b, ministral-8b, llama-8b, smollm3-3b]
      prompts: [content-only, structure-aware]
      apply_to: all
    - id: intermediate-escalation
      models: [gemma-12b, mistral-small-24b, glm-4-9b]
      prompts: [content-only, structure-aware]
      apply_to: unresolved
    - id: escalation
      models: [qwen3-14b, exaone-32b]
      prompts:
        - content-only
        - structure-aware
        - reference-aware
        - bounded-reasoning
      apply_to: unresolved
```

This keeps the first stage focused on the semantic baseline and the productive
structure-aware variant. More expensive or specialised prompts are evaluated only for
unresolved clauses in later stages. Qualification reports contain only combinations that
were configured for the respective model; intentionally omitted combinations are not
reported as missing runs.

Models may also declare dimension-specific voting eligibility. This keeps the complete model
prediction in the qualification artifacts while excluding a model from a semantic subtask for
which qualification showed systematic weakness. Eligibility affects only consensus arithmetic;
it does not suppress inference or diagnostics.

```yaml
models:
  - id: smollm3-3b
    provider: ramalama
    dimension_eligibility:
      applicability_presence: true
      applicability_polarity: false
```

An ineligible vote is removed from both numerator and denominator. For example, if SmolLM3 is
ineligible for `applicability_polarity`, three remaining positive-presence polarity voters with two `included`
votes and one `excluded` vote yield `2/3`, not `2/4`. Applicability presence is
calculated independently, so SmolLM3 can still contribute to the presence decision. Omitted
eligibility settings default to `true` for backward compatibility.


### Taxonomy distinctions

The semantic profile distinguishes `recommendation` (typically “should”) from
`condemnation` (typically “should not”). A condemnation is a negative
recommendation and must not be classified as a prohibition unless the source
uses mandatory negative language such as “shall not”.

The `warning` function identifies statements that draw attention to a risk,
limitation, unsafe consequence, unreliable result, invalid assumption, or possible
misuse. A warning can qualify an otherwise positive `description`, for example in a
clause that first presents a useful method and then introduces limitations with
“However, ...”. The connective alone is not sufficient: the clause must express an
adverse consequence or risk. Unlike `recommendation` and `condemnation`, `warning`
does not itself prescribe what should or should not be done.

Engineering methods and measures share the `method_or_measure` knowledge kind.
The distinction is not sufficiently stable or useful for qualification to justify
separate model labels. Existing v2 results containing `method` or `measure` must
be regenerated.

## Qualification analysis artifacts

A consensus-enabled qualification-matrix run writes two analysis artifacts beside the
matrix report:

- `cascade-provenance.json` records clause-level entry and exit reasons for every cascade
  stage, configured versus effective resolution policy, and per-dimension resolution
  counts before and after the stage;
- `qualification-analysis-metrics.json` summarizes consensus categories, dimension
  categories, overall resolution states, participation, review reasons, resolution sources,
  and observed versus unresolved structural conflicts.

The command also creates an immutable qualification-run archive directly below
`local/evaluation/`, for example `qualification-run-012.zip`. Run numbers are monotonic and
are never reused by `--overwrite`. The archive contains the qualification manifest snapshot,
qualification and consensus reports, Golden Corpus proposal, HITL queue, analysis metrics,
cascade provenance, cascade JSON reports, and an `archive-manifest.json` with SHA-256 hashes
and file sizes. It also snapshots the exact corpus dataset and corpus manifest, task contract
and schema, all referenced prompt resources, all ontology definitions used by the task,
local/published annotation evidence, and the LLM/MCP runtime configuration files.

Corpus examples include the materialized structural taxonomy context when available. This
means structure-aware qualification requests receive node/leaf kind, ancestor and sibling
context, structural reference edges, scope mentions and resolved/deferred scope edges from
the document taxonomy rather than reconstructing that evidence inside the LLM workflow. Prompt families remain
isolated: only prompt templates that explicitly request `context_json` expose this structural
context to the adaptive LLM interview; content-only and bounded-reasoning prompts do not.

Each ZIP also contains `qualification-run-metadata.json`. This is the canonical description
of the archived run and records the Standards Atlas version, qualification-manifest schema,
matrix and corpus IDs, task and dataset versions, prompt versions, model references,
manifest hash, and result metrics. `local/evaluation/qualification-run-index.json` is a
compact derived index for locating and comparing archived runs without opening every ZIP.

The cascade keeps the manifest's configured thresholds as provenance. Its effective
statement-function confidence floor is raised when necessary to match the downstream
majority auto-acceptance threshold. This prevents a `2/3` majority from being frozen as a
final cascade decision when the review policy would immediately reject that same
confidence.

Structural applicability conflicts have separate observed and unresolved states. An
observed conflict remains available for audit after a later stage resolves it; only an
unresolved structural conflict forces final review.

Applicability cascade resolution treats **presence** and **polarity** as separate hierarchical decisions.
Presence disagreement/confidence determines whether the clause is applicability-relevant at all;
polarity disagreement/confidence is evaluated only after the cumulative decision is positive. A
negative presence decision therefore cannot be escalated because of polarity votes. The
diagnostics report also records how many applicability-driven entries each cascade stage resolves
and how many leave the stage still unresolved.

Use `--overwrite` after changing cascade resolution semantics when the goal is to measure
execution behavior itself. `--recompute` can rebuild derived metrics from persisted
observations, but it cannot retroactively change which clauses earlier runs sent to later
model stages.

## Plan or run the complete qualification workflow

The workflow CLI has two operations, `plan` and `run`. Select the actual workflow with
`--task`. The default task is `documents`; use `--task qualification` for the complete
path from existing extraction artifacts through Markdown publication, corpus construction,
and the qualification matrix:

```bash
uv run standards-atlas workflow plan \
  --task qualification \
  --manifests \
    manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety \
  --corpus-count 500 \
  --corpus-strategy representative_stratified \
  --corpus-seed 20260818 \
  --overwrite
```

Replace `plan` with `run` to execute the same task. The qualification task deliberately
stops document publication at Markdown and never contains Doorstop export or Doorstop
publication steps. By default it reuses existing `.atlas/docling` artifacts. Add
`--regenerate-docling` to regenerate Docling and all downstream artifacts.

Workflow inputs are supplied through the repeatable `--manifests` option. Each file declares
its role through the common `manifest_type` and `schema_version` header. The
`qualification_matrix` manifest is the source of truth for `matrix_id`, `corpus_id`, and the
semantic task version used by corpus construction. The canonical checked-in qualification
manifest is
`manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml`.

`--overwrite` applies replacement policy to derived artifacts and regenerates qualification
proposals, but it does not bypass the shared LLM response cache. Add `--fresh` when the
qualification run must perform new provider inference: the matrix disables proposal reuse and
the LLM response cache, and semantic extraction regenerates the selected clauses with the cache
disabled. `--keep` may be repeated to preserve selected document stages and requires
`--overwrite`. Use `workflow plan` first when you want to inspect the exact command sequence
without side effects.

## Challenger qualification

The qualification-matrix manifest is also the single source of truth for model challenger
experiments. Optional `challenger_qualification` configuration declares challenger model
definitions separately from the production `models` pool and groups them with the incumbent
models whose cascade roles they challenge. A normal `qualification-matrix` run ignores these
challenger-only models.

The applicability hard-case qualification promoted SmolLM3 3B, GLM-4 9B, and EXAONE
3.5 32B into the production cascade. The representative 500-clause follow-up then moved
Ministral 3 8B into `efficient-local` and Gemma 3 12B into `intermediate-escalation` to reduce
Mistral-family correlation in the resolver stage. Slice 3c further narrows applicability-presence
voting after the Slice 3b representative run exposed GLM-4 and SmolLM3 as opposite calibration
extremes. Both remain production voters for other semantic dimensions, but neither contributes to
`applicability_presence`; SmolLM3 also remains excluded from `applicability_polarity`. The displaced
Qwen3 8B, Phi-4 14B, and Qwen3 32B models remain in `challenger_qualification.models` as regression baselines. This keeps the
head-to-head workflow useful without duplicating a model between the production and challenger
pools. Challenger comparison aggregates only `qualification_eligible` candidates; unsupported
or non-executed candidate rows do not dilute model-level success or duration metrics.

Run the isolated comparison with:

```bash
uv run standards-atlas evaluation challenger-qualification \
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --output local/evaluation/challenger
```

Fresh provider inference is the default for challenger runs. Use `--allow-reuse` only for
iterative diagnostics where cached or persisted results are acceptable. The command derives
a separate `<matrix-id>-challengers` full matrix, disables production adjudication, and keeps
the productive cascade unchanged.

For targeted semantic qualification, reuse the difficult applicability clauses from an earlier
qualification-run archive instead of taking the first clauses with `--limit`:

```bash
uv run standards-atlas evaluation challenger-qualification \
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --output local/evaluation/challenger \
  --sample applicability-conflicts \
  --sample-from local/evaluation/qualification-run-005.zip
```

`applicability-conflicts` selects clauses whose final archived model votes disagree either on
applicability presence or, among positive votes, on binary applicability polarity. The source
archive must use the same corpus and dataset version as the current manifest. The exact clause
IDs and source archive are persisted as `challenger-sample-selection.json` and included in the
qualification-run archive. `--limit` may be added to shorten a hard-case smoke test; it limits
the selected hard-case set rather than the start of the corpus.

The challenger run emits the normal qualification and diagnostics artifacts plus
`challenger-comparison.json` and `challenger-comparison.md`. Both comparison artifacts are
created before the immutable qualification-run archive is written and are included in that
archive. The comparison groups incumbents and challengers by cascade role and reports
applicability conflict `none` rate, reference agreement for applicability presence and polarity,
prediction success, and measured duration. These signals are observational and do not
automatically replace, weight, or promote models.

All v3 semantic prompts use the same confidence contract: confidence is a JSON number from
`0.0` through `1.0` (for example, `0.95`), never a percentage such as `95` or `95%`. Invalid
confidence values remain validation failures; the evaluation pipeline does not silently
normalize percentages because prediction success is part of model qualification.

## Focused role golden corpus

Role semantics are qualified against a focused corpus independently of the broad semantic-profile corpus.
The repository provides `manifests/role-relation-golden-corpus-v1.yaml`, which targets 140 clauses across
explicit relations, multiple relations, passive wording without an actor, organizational relations,
role terminology without a relation, negative cases, and structured tables.

Build the review corpus from existing EngineeringDocuments:

```bash
uv run standards-atlas evaluation role-corpus-build \
  --manifest manifests/role-relation-golden-corpus-v1.yaml
```

The command writes machine artifacts (`dataset.json` and `corpus-manifest.yaml`) below `.atlas/` and a
flat HITL file to
`local/review/role-relation-extraction/1.0.0/role-golden-review.csv`. The CSV is the only file a reviewer
should edit. Family-level aggregate documents are excluded when persisted part documents exist, so a
multipart standard contributes clauses from keys such as `EN50126-2`, not the aggregate `EN50126`. The
human-facing `reference` is always fully qualified with that part key. The CSV contains one prepared row per
selected clause with the original text and these review fields: `review_status`, `role_semantics_present`,
`actor`, `relation`, `target`, `condition`, `evidence`, and `review_note`. Internal `clause_id` and
`content_hash` columns are kept at the end of the CSV and normally need no reviewer attention. No YAML
structures need to be created manually.

Set `review_status` to `published` for reviewed cases or `rejected` for unsuitable samples. For a positive
case without a complete explicit actor-relation-target tuple, set `role_semantics_present=true` and leave the
relation columns empty. For multiple relations, duplicate the clause row and fill another relation; repeated
status and presence fields may be left blank on additional rows. Re-running `role-corpus-build` preserves an
existing review CSV instead of overwriting human edits.

Compile the reviewed rows into the machine-readable golden corpus:

```bash
uv run standards-atlas evaluation role-corpus-publish \
  --review local/review/role-relation-extraction/1.0.0/role-golden-review.csv \
  --manifest .atlas/data/evaluation/corpora/role-relation-extraction/1.0.0/corpus-manifest.yaml
```

By default, the command writes `role-golden-corpus.yaml` next to the corpus manifest. Only `published` rows are compiled into the golden corpus; `pending` and `rejected` rows do not contribute
to regression metrics. After a qualification run, compare its `consensus-report.json` with the published role
gold:

```bash
uv run standards-atlas evaluation role-corpus-evaluate \
  --golden .atlas/data/evaluation/corpora/role-relation-extraction/1.0.0/role-golden-corpus.yaml \
  --consensus local/review/qualification/consensus/consensus-report.json \
  --output local/evaluation/qualification/role-golden-regression.json
```

The regression report separates presence accuracy/precision/recall/F1 from exact normalized
actor-relation_class-target tuple precision/recall/F1. This prevents a conservative all-negative presence
consensus from appearing equivalent to correct relation extraction.

### Applicability semantic boundary

Qualification task 2.4.0 treats applicability as one hierarchical qualification dimension:
**presence first, binary polarity second**. `applicability_present` decides whether the clause
explicitly includes or excludes normative content for a stated subject or case. When presence is
positive, the qualification prompt permits exactly one transport label: `inclusion` (projected to
`included`) or `exclusion` (projected to `excluded`). `exception` and `applicability_condition` are
not qualification labels in this stage. Conditional wording that only changes how an activity or
method is performed is not applicability.

The canonical semantic task remains broader because those concepts may still be useful outside
qualification. The `structure-aware-v8` qualification prompt therefore uses a safe narrowing of the
canonical structured-output schema rather than changing the ontology or EngineeringDocument
contract.

Use `manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml`
for the production cascade. Its structure-aware applicability vote uses `structure-aware-v8`.


### Applicability presence model eligibility

Slice 3c applies model eligibility independently from prompt and ontology semantics. The v5
manifest excludes GLM-4 9B and SmolLM3 3B from `applicability_presence` voting because the
Slice 3b representative run showed opposite calibration extremes (strongly permissive versus
strongly conservative). Their predictions are still produced and remain available for diagnostics
and for semantic dimensions where they are eligible.

Eligibility is cumulative across cascade stages. The configured production cascade retains three
eligible applicability-presence voters after `efficient-local`, five after
`intermediate-escalation`, and seven after final escalation. Manifest validation rejects filtered
cascade configurations that would leave fewer dimension-eligible voters than a stage's configured
`minimum_successful_models`. Applicability-polarity eligibility is independent from presence
eligibility; a model may therefore remain useful for included/excluded discrimination even when it is not
trusted to decide whether applicability semantics are present at all.

### Role qualification contract

The current semantic-profile qualification contract uses the same open role-relation model as
production extraction and the role golden corpus. Each extracted relation contains `actor`,
`relation_class`, and `target`. `relation_class` is open; the documented core classes are recommendations rather
than a closed enum. `predicate` preserves the evidence-grounded verb or verb phrase.

Passive role/action semantics may set `role_semantics_present=true` while returning an empty
`role_relations` list. The qualification prompt must not invent an actor that is not explicit in
the clause. Legacy scalar fields such as `role_relation_types` and
`primary_role_relation_type` are not part of the current 2.4.0/v6 generation contract; they are
retained only when reading archived qualification data.


### Role actor boundaries

The current role prompts distinguish an actor from a grammatical subject. A role actor must be an explicitly identified human or organizational role, person, group, organization, organizational unit, committee/body, supplier, duty holder, authority, or stakeholder. Technical objects such as systems, software, documents, requirements, test conditions, and safety integrity levels are not actors merely because they are sentence subjects.

Passive role/action semantics remain positive for `role_semantics_present` when the action is role-like but the actor is omitted. For example, `A hazard analysis shall be performed` is role semantics with no extractable relation tuple. In contrast, `The system shall satisfy the requirements` is not role semantics. Relation extraction must never infer the missing actor.

Targets must be the explicit object or subject matter toward which the predicate is directed and must not simply repeat the actor unless the clause explicitly states a reflexive relation. Applicability, scope, technical properties, and logical conditions must not leak into `role_relations`.

### Applicability qualification golden set

Applicability qualification uses a HITL-reviewed contract with `present` plus an optional binary `polarity` (`included` or `excluded`). Exception and generic condition semantics are outside this qualification stage. Schema 2.1 makes the corpus incremental: provenance is recorded per case, and new review batches can exclude clauses that are already published in an existing golden corpus. Legacy `applicability_function`/subtype fields and schema-2.0 corpus-level run provenance are not accepted.

Build the first review batch from a qualification archive:

```bash
uv run standards-atlas evaluation applicability-corpus-build \
  --run local/evaluation/qualification-run-066.zip \
  --limit 30
```

The command writes `local/review/applicability/2.1.0/applicability-golden-review.csv`. Selection is deterministic and stratified across balanced presence disagreement, minority presence disagreement, framing-sensitive presence, and polarity disagreement. Within strata, document round-robin selection reduces domination by a single standard or part. Unused quota spills deterministically into the remaining candidate pool. The CLI reports candidate counts, exclusions, per-category selection accounting, and represented documents. The CSV also records vote counts, disagreement scores, participating model groups, and selection rank so that the selection decision remains auditable.

Set `review_status=published`, review `present`, and set `polarity` to `included` or `excluded` when presence is true and the direction is clear. Publish the initial corpus with:

```bash
uv run standards-atlas evaluation applicability-corpus-publish \
  --review local/review/applicability/2.1.0/applicability-golden-review.csv \
  --run local/evaluation/qualification-run-066.zip
```

For a later qualification run, exclude already-published clauses during review construction:

```bash
uv run standards-atlas evaluation applicability-corpus-build \
  --run local/evaluation/qualification-run-067.zip \
  --golden local/review/applicability/2.1.0/applicability-golden-corpus.yaml \
  --limit 30
```

After review, merge the newly published cases into the existing corpus:

```bash
uv run standards-atlas evaluation applicability-corpus-publish \
  --review local/review/applicability/2.1.0/applicability-golden-review.csv \
  --run local/evaluation/qualification-run-067.zip \
  --golden local/review/applicability/2.1.0/applicability-golden-corpus.yaml \
  --output local/review/applicability/2.1.0/applicability-golden-corpus.yaml
```

Re-publishing an already known clause with the same gold annotation is idempotent. A different `present` or `polarity` annotation for an existing `(document_key, clause_id)` is rejected instead of silently overwriting reviewed ground truth. Each published case retains the source qualification archive name and SHA256 digest.

Evaluate the enlarged corpus with:

```bash
uv run standards-atlas evaluation applicability-corpus-evaluate \
  --golden local/review/applicability/2.1.0/applicability-golden-corpus.yaml \
  --run local/evaluation/qualification-run-067.zip \
  --output local/evaluation/qualification/applicability-golden-regression.json
```

The regression report contains consensus metrics, presence precision/recall/F1, and binary polarity accuracy for every model represented in the archived run. The golden corpus is deliberately a diagnostic hard-case corpus rather than a representative random sample; use its reviewed metrics for calibration and regression analysis rather than interpreting the class balance as corpus prevalence.

### Applicability boundary prompt matrix

Analyze clause-level applicability presence disagreements from an immutable qualification run with:

```bash
uv run standards-atlas evaluation applicability-hard-cases \
  local/evaluation/qualification-run-064.zip \
  --output local/evaluation/applicability-hard-cases
```

The analyzer ranks balanced and minority presence disagreements before framing-sensitive and polarity-only cases, reports per-model presence profiles, and writes JSON, Markdown, and a HITL-ready review CSV. New qualification archives include the compact `applicability-predictions.json` snapshot required for this retrospective analysis; older archives without clause-level predictions cannot be reconstructed from aggregate metrics alone.

The dedicated manifest `manifests/multidimensional-semantic-qualification-v5-applicability-framing-v1.yaml` is a two-arm full-matrix prompt experiment. Both arms use the same model set and the complete deterministic `full-context-v1` CBox, so only the prompt wording changes:

- `applicability-boundary` uses `structure-aware-v9` with the core question and explicit conceptual boundaries.
- `applicability-boundary-examples` uses `structure-aware-v9-examples` with the same rules plus one positive and one negative technique-or-method example.

This isolates the effect of the examples from CBox framing. Both prompts treat an explicit statement about the applicability of a technique, method, or measure as positive applicability evidence, while a condition that only changes how it is performed remains negative. When a clause contains explicit applicability statements in both directions, presence stays positive and polarity remains empty.

Qualification archives retain the matrix id, prompt candidate id, prompt resource version, CBox frame, model id, and clause-level predictions. New results can therefore be compared with archived `structure-aware-v8` results by evaluating both archives against the same published golden corpus. Recompute the regression report for older archives after the golden corpus changes; previously generated aggregate reports still reflect the earlier HITL labels.

### Knowledge qualification

Knowledge qualification distinguishes the primary knowledge kind from the complete multi-label knowledge set. The active cascade accepts a primary knowledge decision once its support reaches the configured 0.60 majority threshold; mere non-unanimity is not an escalation reason. Differences in secondary knowledge kinds are reported separately through `knowledge_set_category` and `knowledge_set_confidence`; they do not by themselves trigger an escalation. `knowledge_kind_category` remains a compatibility alias for the primary decision.

### Ontology-guided semantic extraction

Semantic-extraction progress and failure diagnostics use the human-readable standard clause reference (and title when available), with the internal `clause-…` identifier shown only as a technical trace key. Relations in the structured LLM response refer to zero-based positions in the returned entity array, so model-generated entity IDs cannot collide.


A qualification-matrix manifest can enable `semantic_extraction_qualification`. The end-to-end `workflow run --task qualification` appends a `semantic-extraction-qualification` step after the normal semantic matrix and defers immutable run-archive creation until both stages have completed. For qualification runs, extraction eligibility is derived from the latest available cascade consensus for each selected clause; those semantics are supplied as transient extraction context and are not written back into the canonical `EngineeringDocument`. The extraction report records the resolved model plus selected, contextualized, eligible, attempted, extracted, failed, and skipped clause counts. The extractor prints clause-level progress while it runs, including the current/total attempt, document and clause ID, outcome, entity/relation counts, and elapsed time. `semantic_extraction_qualification.timeout_seconds` controls the per-clause LLM timeout independently of the default endpoint configuration. LLM timeouts, invalid responses, and temporary endpoint failures are isolated to the affected clause, persisted as extraction failures, reported separately, and do not abort processing of later clauses. The final `qualification-run-NNN.zip` contains `semantic-extraction-qualification.json`, run-scoped semantic-extraction snapshots including failed clauses, and the exact formal OWL ontology resources used for qualification. `qualification-run-metadata.json` records the semantic-extraction metrics in a dedicated section. Limited runs archive only the extraction clauses selected by the same dataset slice used by the matrix. Ontology conformance and confidence gates are always reported. Undeclared OWL classes/properties are rejected without aborting the run and are reported with per-term counts; relations that cannot be retained because they reference rejected entities are reported separately as invalid relations. Gold precision, recall, and F1 remain unset until a published extraction gold file is configured in the manifest.
