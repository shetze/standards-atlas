# Troubleshooting

## Start with inspection

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
uv run standards-atlas workflow plan --catalog catalogs/standards.yaml --family FAMILY
uv run standards-atlas docling inspect DOCUMENT
uv run standards-atlas normalize inspect DOCUMENT
uv run standards-atlas references inspect DOCUMENT
uv run standards-atlas align inspect DOCUMENT
```

## Workflow pauses at review

This is expected. Export or complete the requested alignment or AtlasData review, then rerun with `--continue-after-review`.

## Part conflicts with a year

Ensure the catalog declares the physical document's part separately from its publication year. Filenames alone are not authoritative metadata.

## No persisted document found

A downstream command was run before import, onboarding, enrichment, or composition produced `.atlas/documents/<key>.json`.

## Missing clauses after alignment

Inspect content selection first, then normalized headings and candidate detection. A missing source page cannot be repaired by alignment heuristics.

## Docling conversion already exists

Treat conversion as private source evidence. Remove it deliberately only after confirming that regeneration is intended; `--force` is not a blanket overwrite switch.

## Doorstop hierarchy is wrong

Check catalog knowledge-domain relationships and verify that every part has a clause `0` root before export.
