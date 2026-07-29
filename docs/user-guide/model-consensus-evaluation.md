# Model-consensus semantic evaluation

The semantic evaluation follows the existing processing chain rather than introducing another workflow manifest.

```bash
uv run standards-atlas workflow run \
  --catalog catalogs/standards.yaml \
  --hierarchy functional-safety

uv run standards-atlas evaluation corpus-build \
  --task statement-function-classification \
  --version 1.0.0 \
  --corpus-id semantic-roles-v1 \
  --knowledge-domain functional-safety \
  --count 500 \
  --strategy representative_stratified \
  --seed 20260728

uv run standards-atlas evaluation qualification-matrix \
  --manifest local/evaluation/qualification/semantic-role-v1.yaml \
  --output local/evaluation/qualification
```

The qualification manifest defines models, prompts, repetitions, optional imports of existing HITL reviews, and consensus thresholds. Consensus should select a text-focused prompt such as `content-only`; structural roles are not part of this comparison.

For every clause, repetitions are first collapsed into one vote per model. The model votes are then classified as unanimous, strong consensus, majority consensus, disputed, or insufficient evidence.

The command writes these additional artifacts below the configured consensus output directory:

- `consensus-report.json`: complete model votes and support values;
- `golden-corpus-proposal.yaml`: proposed statement functions and confidence;
- `consensus-review.md`: only cases requiring focused HITL resolution.

Existing reviewed annotations can be imported before execution through `review_imports` in the same manifest. They are used by the existing qualification metrics, while the new proposal is derived independently from cross-model agreement.
