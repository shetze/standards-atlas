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
