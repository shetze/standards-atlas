# Getting started

## Prerequisites

- Python 3.13
- `uv`
- access to the source PDFs that you are permitted to process
- a Git working tree for reproducible review and change control

## Install

```bash
uv sync --dev
uv run standards-atlas --version
uv run standards-atlas catalog validate manifests/standards.yaml
```

Docling is installed as a project dependency. Its conversion output is private source-derived material and belongs under `.atlas/`, not in a public repository.

## Inspect the workflow before running it

```bash
uv run standards-atlas workflow plan \
  --manifests manifests/standards.yaml \
  --family EN50716
```

The plan lists deterministic steps and marks manual review gates.

## Run one family

```bash
uv run standards-atlas workflow run \
  --manifests manifests/standards.yaml \
  --family EN50716
```

The first run normally pauses at a review gate. Complete the generated alignment or AtlasData review, then continue:

```bash
uv run standards-atlas workflow run \
  --manifests manifests/standards.yaml \
  --family EN50716 \
  --continue-after-review
```

## Run a profile or the complete catalog

```bash
uv run standards-atlas workflow plan --manifests manifests/standards.yaml --profile railway
uv run standards-atlas workflow run --manifests manifests/standards.yaml --all
```

Use `--force` only to regenerate artefacts for commands that explicitly support safe replacement. It does not authorize destructive replacement of private Docling conversion results.
