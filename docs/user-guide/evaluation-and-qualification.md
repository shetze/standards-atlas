# Evaluation and qualification

The evaluation subsystem separates datasets, proposal runs, human review, metrics and published evidence. Generated model output is never automatically equivalent to a gold standard.

## Build a representative corpus

```bash
uv run standards-atlas evaluation corpus-build   --task semantic-role-classification   --version 1.0.0   --corpus-id semantic-roles-v1   --knowledge-domain functional-safety   --count 500   --strategy representative_stratified   --seed 20260728
```

Legacy task and corpus identifiers may remain in existing data. New classification work should use the multi-dimensional structural-profile model and domain-specific taxonomies.

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
