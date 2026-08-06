# Model-consensus evaluation

Model consensus is a proposal mechanism for focusing human review. It is not an independent source of truth.

Run the configured qualification matrix first:

```bash
uv run standards-atlas evaluation qualification-matrix   --manifest local/evaluation/qualification/semantic-role-v1.yaml   --output local/evaluation/qualification
```

Repeated predictions are collapsed per model before votes are compared across models. Reports distinguish unanimous agreement, strong or majority consensus, disputes and insufficient evidence.

Reviewers must consider proposal anchoring: a plausible proposal from a strong model can survive simply because interpreting difficult clauses is expensive. Therefore:

- preserve the original clause and structural evidence;
- expose disagreement and insufficient-evidence cases prominently;
- keep generated proposals separate from reviewer decisions;
- evaluate each taxonomy dimension independently;
- permit an explicit unclassified result.

Historical files may still use `semantic-role` names. The current domain model uses multi-dimensional `StructuralProfile` data.

## Structural evidence and deterministic fusion

The consensus stage evaluates statement functions in three conceptual steps:

1. derive high-confidence evidence from normalized structure and explicit wording;
2. retain the independent text classifications produced by every model;
3. fuse both sources deterministically into the Golden Corpus proposal.

Explicit function-bearing titles such as `Example`, `Style Guide`, `Definition`,
`Objective`, `Rationale`, `Assumption`, `Prerequisite`, `Note`, `Warning`, or
`Caution` can determine the proposed primary statement function. Conservative
lexical evidence can add functions such as `condemnation` for `should not`,
`prohibition` for `shall not`, or `warning` for an explicit warning marker with
an adverse consequence.

Structural evidence does not rewrite individual model votes. The consensus
report records it separately under `structural_prior`, so reviewers can compare
model behavior with the deterministic fusion decision. A structural override is
reported as strong rather than unanimous consensus when the models themselves
voted for another primary function.
