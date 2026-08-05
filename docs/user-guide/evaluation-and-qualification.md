# Evaluation and qualification

The evaluation subsystem separates datasets, proposal runs, human review, metrics and published evidence. Generated model output is never automatically equivalent to a gold standard.

## Build a representative corpus

```bash
uv run standards-atlas evaluation corpus-build \
  --task statement-function-classification \
  --version 2.0.0 \
  --corpus-id statement-functions-v2 \
  --knowledge-domain functional-safety \
  --count 500 \
  --strategy representative_stratified \
  --seed 20260804
```

The command remains the standard entry point for statement-function qualification. The
task metadata and central eligibility policy exclude `table_dominant` clauses by default.
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

## Execute a qualification matrix

```bash
uv run standards-atlas evaluation qualification-matrix   --manifest local/evaluation/qualification/semantic-role-v1.yaml   --output local/evaluation/qualification
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
      models: [granite, gemma, mistral]
      prompts: [content-only, structure-aware]
      apply_to: all
    - id: prompt-refinement
      models: [qwen-14b, qwen-32b]
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


### Taxonomy distinctions

The semantic profile distinguishes `recommendation` (typically “should”) from
`condemnation` (typically “should not”). A condemnation is a negative
recommendation and must not be classified as a prohibition unless the source
uses mandatory negative language such as “shall not”.

Engineering methods and measures share the `method_or_measure` knowledge kind.
The distinction is not sufficiently stable or useful for qualification to justify
separate model labels. Existing v2 results containing `method` or `measure` must
be regenerated.
