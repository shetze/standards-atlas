# Docling integration

The Docling adapter converts PDF source documents into Docling's native JSON representation and stores the result below the private `.atlas` workspace.

## Tested configuration

The adapter targets Python 3.12 or newer and Docling `>=2.112,<3`. The exact Docling version, source hash, conversion timestamp, and effective conversion options are persisted in `conversion.json` for every conversion.

## Installation

```bash
uv sync --extra docling
```

## Conversion

```bash
uv run standards-atlas docling convert \
  tests/fixtures/pdf/minimal-standard.pdf \
  --document MIN-STD
```

A repeated call reuses the existing extraction when its source hash still matches. A changed source is reported as stale and requires `--overwrite`.

## Inspection

```bash
uv run standards-atlas docling inspect MIN-STD
```

Inspection reads the persisted JSON without loading Docling. It reports item counts, page-evidence coverage, and unknown Docling labels.

## Tests

The normal unit suite uses synthetic native JSON fixtures and does not require Docling:

```bash
uv run pytest -m "not docling"
```

The real conversion test uses the self-authored PDF fixture:

```bash
uv run pytest -m docling
```

No copyrighted standard content is stored in the repository.
