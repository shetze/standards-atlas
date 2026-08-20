# Semantic annotation review

Slice 5.4.4 turns generated semantic-role proposals into reviewed, publishable corpus annotations.

## Export reviews

Choose the concrete proposal run produced by `evaluation annotations-propose` and a local review
directory:

```bash
uv run standards-atlas evaluation annotations-review-export \
  --run local/evaluation/runs/<corpus>/<prompt>/<provider>/<model> \
  --reviews local/evaluation/reviews/<corpus>/<prompt>/<provider>/<model>
```

Each clause receives one Markdown file. The file contains local review context and an embedded YAML
block. Edit only that block. Set `reviewer`; `reviewed_at` may remain empty and will then be filled
with the import time in UTC.

Use `accepted` when the generated selection is correct, `corrected` when roles must change,
`rejected` when no role should be assigned, and `ambiguous` when the clause cannot be classified
unambiguously.

## Import reviews

```bash
uv run standards-atlas evaluation annotations-review-import \
  --corpus-id <corpus> \
  --run local/evaluation/runs/<corpus>/<prompt>/<provider>/<model> \
  --reviews local/evaluation/reviews/<corpus>/<prompt>/<provider>/<model>
```

The importer validates proposal identity, content hashes, decision consistency, role names, primary
role membership, duplicates, and conflicts with existing reviewed annotations. Canonical reviewed
annotations are written below `local/review/semantic-annotations/<corpus>`.

## Publish reviewed data

```bash
uv run standards-atlas evaluation annotations-publish --corpus-id <corpus>
```

Reviewed annotations and the corpus manifest are copied to `data/evaluation/corpora`. Published
annotations take precedence over local proposals and reviews. Review Markdown and clause text are
never published by this command.
