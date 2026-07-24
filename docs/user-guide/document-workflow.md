# Document workflow

![Detailed processing pipeline](../architecture/diagrams/svg/processing-pipeline.svg)

## Convert

```bash
uv run standards-atlas docling convert SOURCE.pdf --document-key EN50716
```

Conversion persists native Docling JSON and metadata below `.atlas/docling/`.

## Inspect extraction

```bash
uv run standards-atlas docling inspect EN50716
```

Inspect page selection, headings, tables, lists, captions, and conversion warnings before continuing.

## Normalize

```bash
uv run standards-atlas normalize run EN50716
uv run standards-atlas normalize inspect EN50716
```

Normalization must preserve all source content and evidence. A detected loss raises an error rather than producing a partial semantic input.

## Detect references

```bash
uv run standards-atlas references detect EN50716
uv run standards-atlas references inspect EN50716
```

Detection identifies clause-number candidates, annex references, headings, and page anchors without deciding the final match.

## Align

```bash
uv run standards-atlas align run EN50716 data/EN50716
uv run standards-atlas align inspect EN50716
```

Alignment combines deterministic evidence and confidence data. Low-confidence or missing clauses remain visible for review.

## Construct and enrich documents

Depending on the source and workflow, use AtlasData import, Docling onboarding, content enrichment, part derivation, or family composition. Persisted `EngineeringDocument` objects live below `.atlas/documents/`.
