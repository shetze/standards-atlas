# Document workflow

The catalog-driven workflow is the preferred entry point. Individual commands remain useful for diagnosis and controlled development.

## Plan and run

```bash
uv run standards-atlas workflow plan   --catalog catalogs/standards.yaml   --profile functional-safety

uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --profile functional-safety
```

Select exactly one family selection mode. A hierarchy can be processed directly:

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --hierarchy functional-safety
```

Successful runs write JSON and Markdown derivation reports.

## Regeneration modes

- default: reuse valid persisted artefacts and stop on incomplete or incompatible state;
- `--overwrite`: regenerate derived artefacts;
- `--overwrite --keep docling`: regenerate later stages but retain extraction;
- `--force`: regenerate every reproducible stage, including Docling.

`--keep` is repeatable and valid only together with `--overwrite`.

## Run individual stages

### Extract

```bash
uv run standards-atlas docling convert SOURCE.pdf --document EN50716
uv run standards-atlas docling inspect EN50716
```

### Normalize

```bash
uv run standards-atlas normalize run EN50716
uv run standards-atlas normalize inspect EN50716
```

### Detect references

```bash
uv run standards-atlas references detect EN50716
uv run standards-atlas references inspect EN50716
```

### Align and review

```bash
uv run standards-atlas align run EN50716 --atlasdata data/EN50716
uv run standards-atlas align inspect EN50716 --show-conflicts
```

Continue with [Alignment review](alignment-review.md) when the result is uncertain.

### Construct and enrich

The workflow imports the reviewed structure, enriches clauses from aligned normalized ranges, derives parts where required and composes families. Persisted canonical documents are placed below `.atlas/documents/`.

## Review-aware continuation

After completing requested reviews, rerun the same selection with:

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --family EN50716   --continue-after-review
```

This flag does not approve proposals. It only permits execution when the expected reviewed artefacts already exist.
