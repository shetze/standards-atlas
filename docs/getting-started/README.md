# Getting started

## Prerequisites

- Linux development environment
- Git
- `uv`
- Python version selected by `.python-version`
- optional: Docling dependencies for PDF conversion
- optional: RamaLama and a supported GPU/runtime for local model evaluation

## Install the project

```bash
git clone <repository-url> standards-atlas
cd standards-atlas
uv sync --all-extras --dev
```

Check the command tree:

```bash
uv run standards-atlas --help
```

## Validate the shipped catalog

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
```

## Plan before executing

Select exactly one of `--family`, `--profile`, `--all`, or use a configured `--hierarchy`:

```bash
uv run standards-atlas workflow plan   --catalog catalogs/standards.yaml   --family EN50716
```

Planning is read-only. It shows every stage and identifies manual review gates.

## Run a workflow

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --family EN50716
```

A run may pause intentionally for alignment or AtlasData review. Complete the requested review, then continue:

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --family EN50716   --continue-after-review
```

To rebuild derived stages while reusing Docling output:

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --family EN50716   --overwrite   --keep docling
```

`--force` regenerates all reproducible artefacts, including Docling output. It is mutually exclusive with `--overwrite`.

## Next steps

- [Document workflow](../user-guide/document-workflow.md)
- [Workspace](../user-guide/workspace.md)
- [Exports](../user-guide/exports.md)
- [Troubleshooting](../user-guide/troubleshooting.md)
