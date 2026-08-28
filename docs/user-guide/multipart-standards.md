# Multi-part standards

A standard family may be extracted from several PDFs while keeping each physical part as the only canonical EngineeringDocument. Publication builds a runtime-only family projection on demand.

![Multi-part composition](../architecture/diagrams/svg/multipart-composition.svg)

Each part retains its physical source provenance and has exactly one clause `0` root in the canonical representation. Part identifiers are distinct from publication years. Annexes remain addressable and are reported separately during alignment.

Useful commands include:

```bash
uv run standards-atlas document derive-part FAMILY PART
uv run standards-atlas atlasdata onboard-family FAMILY --manifest manifests/standards.yaml
```

Composition validates part identity, root structure, and key uniqueness at export time. No composed family artifact is persisted. The workflow passes the ordered physical part keys to Markdown and Doorstop export; Markdown can emit separate files for all parts in one invocation and Doorstop creates a root item for each part.


## Family AtlasData onboarding

Family onboarding resolves physical Docling artifacts from the standards manifest rather than requiring callers to duplicate every `PART=PATH` mapping. Each part is structurally discovered independently and then rendered into one family AtlasData file with family-wide part-qualified structure identifiers. Optional part-level `publication_year` values preserve mixed-edition families such as IEC 61508.
