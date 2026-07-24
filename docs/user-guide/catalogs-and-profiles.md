# Catalogs and profiles

The YAML catalog is the control plane for repeatable processing. It declares knowledge domains, industry sectors, families, physical documents, content selection, family composition, relationships, and runnable profiles.

Validate every catalog change:

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
```

## Page selection

Use catalog page selection when a PDF contains covers, indexes, bilingual pages, or unrelated material. Supported concepts include contiguous ranges, excluded ranges, and explicit positive page lists. Selection is applied at extraction time and is recorded as provenance.

## Profiles

A profile names a repeatable set of families, for example a railway or automotive set. Profiles avoid copying long `--family` lists into automation.

## Relationships

Catalog relationships drive composed knowledge-domain and Doorstop hierarchies. They must reflect the actual standards relationship rather than a convenient filesystem order.

See [Catalog format](../reference/catalog-format.md) for the field-level reference.
