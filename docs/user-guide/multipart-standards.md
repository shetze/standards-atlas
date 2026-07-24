# Multi-part standards

A standard family may be extracted from several PDFs and still produce one composed engineering view.

![Multi-part composition](../architecture/diagrams/svg/multipart-composition.svg)

Each part retains its physical source provenance and has exactly one clause `0` root in the canonical representation. Part identifiers are distinct from publication years. Annexes remain addressable and are reported separately during alignment.

Useful commands include:

```bash
uv run standards-atlas document derive-part FAMILY PART
uv run standards-atlas document compose-family FAMILY
uv run standards-atlas atlasdata onboard-docling-parts FAMILY DATA_PATH
```

Composition validates part identity, root structure, and key uniqueness. It does not silently merge conflicting clauses. Markdown export can emit separate files for all parts in one invocation; Doorstop export creates a root item for each part.
