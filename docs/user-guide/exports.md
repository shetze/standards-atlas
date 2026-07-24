# Exports

Exports are projections of the canonical `EngineeringDocument`; they are not the internal source of truth.

## Markdown

```bash
uv run standards-atlas document export markdown EN50716 --output-dir build/markdown
```

Markdown preserves clause order, structured content, and a bounded table of contents. Multi-part documents are exported as separate files where appropriate.

## Doorstop

```bash
uv run standards-atlas document export doorstop EN50716 --output-dir build/doorstop
```

Doorstop export creates deterministic identifiers, part roots, parent-child relationships, semantic metadata, and catalog-derived family hierarchy. The result can be validated and published with Doorstop tooling.

## Publication boundary

Only information permitted by annotation visibility and export policy may enter public outputs. Private source artefacts, full copyrighted text, review working files, and local annotations stay in the workspace unless an explicit export contract allows them.
