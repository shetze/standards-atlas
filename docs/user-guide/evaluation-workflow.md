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
