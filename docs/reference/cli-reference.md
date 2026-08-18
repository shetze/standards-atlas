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
- `workflow plan --task documents|qualification`, `workflow run`: plan or execute catalog-driven processing

## AtlasData

- `atlasdata onboard-docling`
- `atlasdata onboard-docling-parts`
- `atlasdata set-status`
- `atlasdata generate-toc`

## Documents and exports

- `document import`
- `document derive`
- `document derive-part`
- `document compose-family`
- `document enrich-content`
- `document export markdown`
- `document export doorstop`

## Extraction and normalization

- `docling convert`, `docling inspect`
- `normalize run`, `normalize inspect`

## References and alignment

- `references detect`, `references inspect`
- `align run`, `align inspect`
- `align review`, `align review-export`
- `align review-validate`, `align review-diff`, `align review-import`
- `align validate-overrides`, `align review-apply`

Use the catalog-driven workflow for routine processing and individual commands for diagnostics or controlled partial execution.
