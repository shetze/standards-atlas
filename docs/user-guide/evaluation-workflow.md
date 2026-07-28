# Local evaluation workflow

Protected standards remain outside Git. Slice 5.3.4 builds annotation-ready corpora from
persisted `EngineeringDocument` clauses and executes reproducible prompt/model matrices.

## Build a local corpus

```bash
uv run standards-atlas evaluation corpus-build \
  --task clause-summary \
  --version local-1 \
  --count 100 \
  --strategy balanced_by_document
```

The corpus is written below `local/evaluation/corpora/` and contains empty `expected`
objects with `annotation_status: proposed`. Reviewers add the task-specific expected
result before benchmarking. `corpus-manifest.json` records the seed, filters, sampling
strategy and SHA-256 source hashes. Use `--hashes-only` for a manifest without clause text.

To use the local corpus, point a benchmark manifest's `resources` field at a root containing
both `prompts/` and `corpora/`, or copy/link the approved local dataset into such a private
resource root.

## Run a prompt/model matrix

```bash
uv run standards-atlas evaluation benchmark \
  --manifest cfg/evaluation/clause-summary.yaml \
  --config cfg/llm.yaml
```

Every prompt version is evaluated against every model using the same dataset. The manifest
hash excludes only the output directory and is embedded into all runs. By default,
`matrix-summary.json` contains metrics, hashes and errors but omits generated and expected
case content. Set `include_case_details: true` only for protected local reports.

## Extract clause references before review

Run deterministic same-document extraction after EngineeringDocuments are available:

```bash
uv run standards-atlas evaluation references-extract \
  --knowledge-domain functional-safety \
  --workspace .atlas \
  --output local/evaluation/references
```

The command writes one YAML analysis per clause. Single references and clause ranges are
resolved against the actual EngineeringDocument structure. Unresolved or ambiguous
references remain as diagnostics. `annotations-review-export` reads this location by
default and adds resolved targets to the HITL document. Use `--reference-root` to select
a different local analysis root.

## Resolve annotations and calculate qualification metrics

After a proposal run and optional human review, calculate the Slice 5.4.5 report:

```bash
uv run standards-atlas evaluation annotations-metrics \
  --corpus-id semantic-roles-v1 \
  --run local/evaluation/runs/semantic-roles-v1/prompt/provider/model
```

The resolver applies `data > local > structure`. Gold Agreement includes only reviewed or
published annotations. Silver Agreement uses the best available annotation or structural
fallback, while Structure Agreement remains a separate baseline. Reports are written as
`qualification.json` and `qualification.md` below `local/evaluation/metrics/` and include
coverage, exact match, primary-role accuracy, micro/macro F1, confusion data, calibration,
and breakdowns by knowledge domain and corpus strata.
