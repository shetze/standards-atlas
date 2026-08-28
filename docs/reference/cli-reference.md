# CLI reference

The authoritative option list is available through `--help` for every command.

```bash
uv run standards-atlas --help
uv run standards-atlas workflow run --help
```

## Top-level commands

- `info`: project information
- `validate`, `trace`: repository validation and traceability helpers
- `inspect data`: inspect legacy data artefacts
- `catalog validate`: validate catalog structure and references
- `workflow plan`, `workflow run`: plan or execute a typed-manifest workflow. The supported workflow tasks are `documents` and `qualification`; `documents` is the default. Qualification workflows accept `--limit` for a shared execution slice and `--fresh` to bypass proposal reuse and LLM response caches across matrix and semantic-extraction inference.


### Workflow manifest contract

`workflow plan` and `workflow run` accept workflow configuration through `--manifests`. The option may be repeated and each occurrence may also contain comma-separated paths. The workflow loader selects inputs by each file's `manifest_type`, not by filename or argument order.

```bash
uv run standards-atlas workflow plan \
  --task documents \
  --manifests manifests/standards.yaml \
  --all

uv run standards-atlas workflow plan \
  --task qualification \
  --manifests \
    manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

The unified `--manifests` interface belongs to the workflow envelope. Direct low-level commands remain intentionally specific: for example `evaluation qualification-matrix`, `evaluation challenger-qualification`, and `llm preload-qualification-models` use their own singular `--manifest` option because they consume one qualification-matrix manifest rather than a heterogeneous workflow manifest set.

## AtlasData

- `atlasdata onboard-docling`
- `atlasdata onboard-docling-parts`
- `atlasdata onboard-family`: manifest-driven multipart family onboarding
- `atlasdata set-status`
- `atlasdata generate-toc`

## Documents and exports

- `document import`
- `document derive`
- `document derive-part`
- `document enrich-content`
- `document classify-taxonomy`
- `document enrich-semantics`
- `document export markdown`
- `document export doorstop`

## Extraction and normalization

- `docling convert`, `docling inspect`
- `normalize run`, `normalize inspect`

## Evaluation and qualification

- `evaluation corpus-build`: build a representative reusable clause corpus
- `evaluation qualification-matrix`: execute multidimensional semantic model qualification
- `evaluation challenger-qualification`: compare configured challenger and incumbent models without changing the production cascade
- `evaluation normalization-quality`: run read-only linguistic-integrity qualification over an
  existing `dataset.json`; semantic labels are ignored

Example exploratory comparison using model definitions already present in the qualification
manifest:

```bash
uv run standards-atlas evaluation normalization-quality \
  --corpus .atlas/data/evaluation/corpora/semantic-profile/2.1.0/dataset.json \
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --output local/evaluation/normalization-quality
```

By default the command selects the configured Mistral Small 3.2 24B and Gemma 3 12B candidates
when available. Repeat `--model MODEL_ID` to choose an explicit comparison set. `--limit` supports
small trial runs and `--no-cache` forces fresh inference. Outputs are `qualification.json`,
`findings.jsonl`, and `qualification.md`. The command never modifies an EngineeringDocument.

## References and alignment

- `references detect`, `references inspect`
- `align run`, `align inspect`
- `align review`, `align review-export`
- `align review-validate`, `align review-diff`, `align review-import`
- `align validate-overrides`, `align review-apply`

Use the catalog-driven workflow for routine processing and individual commands for diagnostics or controlled partial execution.

## `clean`

```bash
uv run standards-atlas clean
uv run standards-atlas clean --cache
uv run standards-atlas clean --data --force
```

The default command removes only `.atlas/work`. `--cache` additionally removes
`.atlas/cache`. Persistent `.atlas/data` requires the explicit destructive
combination `--data --force`. Human-facing `local/` artifacts are never removed.
