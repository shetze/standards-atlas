# Getting started

This is the canonical first-use path for Standards Atlas. The user guide links here rather than maintaining a second installation procedure.

## Prerequisites

- Linux development environment
- Git
- `uv`
- the Python version selected by `.python-version`
- access to source PDFs that you are permitted to process
- optional: RamaLama and a supported GPU/runtime for local model evaluation

## Install the project

```bash
git clone <repository-url> standards-atlas
cd standards-atlas
uv sync --all-extras --dev
```

Check the command tree and installed version:

```bash
uv run standards-atlas --version
uv run standards-atlas --help
```

## Validate the catalog

```bash
uv run standards-atlas catalog validate manifests/standards.yaml
```

The catalog defines source documents, classifications, workflow selections, relationships, and publication settings. See the [catalog reference](../reference/catalog-format.md) before making structural changes.

## Inspect a workflow before running it

Select exactly one of `--family`, `--profile`, `--all`, or a configured `--hierarchy`:

```bash
uv run standards-atlas workflow plan \
  --manifest manifests/standards.yaml \
  --family EN50716
```

Planning is read-only. It lists deterministic stages and marks manual review gates.

Other selections include:

```bash
uv run standards-atlas workflow plan --manifest manifests/standards.yaml --profile railway
uv run standards-atlas workflow plan --manifest manifests/standards.yaml --hierarchy functional-safety
uv run standards-atlas workflow plan --manifest manifests/standards.yaml --all
```

## Run a workflow

```bash
uv run standards-atlas workflow run \
  --manifest manifests/standards.yaml \
  --family EN50716
```

A run may pause intentionally for alignment or AtlasData review. Complete the generated review, then continue:

```bash
uv run standards-atlas workflow run \
  --manifest manifests/standards.yaml \
  --family EN50716 \
  --continue-after-review
```

Private source-derived artefacts, including Docling conversion output, belong below `.atlas/` and must not be committed to a public repository.

## Regeneration options

Use `--force` to regenerate all reproducible artefacts, including Docling output:

```bash
uv run standards-atlas workflow run \
  --manifest manifests/standards.yaml \
  --family EN50716 \
  --force
```

Use `--overwrite` to regenerate derived artefacts and `--keep` to retain selected stages. For example, reuse the existing Docling output:

```bash
uv run standards-atlas workflow run \
  --manifest manifests/standards.yaml \
  --family EN50716 \
  --overwrite \
  --keep docling
```

`--force` and `--overwrite` are mutually exclusive. `--keep` requires `--overwrite` and may be repeated for multiple stages.

## Next steps

- [Concepts](../user-guide/concepts.md)
- [Document workflow](../user-guide/document-workflow.md)
- [Catalogs and profiles](../user-guide/catalogs-and-profiles.md)
- [Workspace](../user-guide/workspace.md)
- [Exports](../user-guide/exports.md)
- [Troubleshooting](../user-guide/troubleshooting.md)
