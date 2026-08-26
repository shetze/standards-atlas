# AtlasData lifecycle

AtlasData is governed as a reviewed public baseline.

![AtlasData lifecycle](../architecture/diagrams/svg/atlasdata-lifecycle.svg)

Typical states are `proposed`, `reviewed`, and `published`. A reviewed baseline is valid for controlled downstream processing; publication marks a baseline intended for public exchange. Status transitions are explicit:

```bash
uv run standards-atlas atlasdata set-status data/EN50716 reviewed
```

Generate or refresh structural TOC data with:

```bash
uv run standards-atlas atlasdata generate-toc data/EN50716
```

Docling headings can create a skeleton for a new baseline:

```bash
uv run standards-atlas atlasdata onboard-docling EN50716 data/EN50716
```

For routine multi-part onboarding prefer the manifest-driven family command:

```bash
uv run standards-atlas atlasdata onboard-family IEC61508 \
  --manifest manifests/standards.yaml
```

The command resolves `.atlas/data/docling/<part-key>/document.json` for every manifest-declared physical part and writes `local/proposed/<family>` by default. `onboard-docling-parts` remains available for diagnostics and explicit `PART=PATH` composition. Supplements are excluded unless `--include-supplements` is requested. Generated headings and types must be reviewed; copyright-protected clause text must not be copied into public AtlasData fields.


## Table structure

Docling onboarding also records table captions and List-of-Tables declarations as public
AtlasData structure. `TABLE` records identify detected tables and their structural parent;
`TABLEINDEX` records represent entries declared by the List of Tables. These records contain
numbering and captions only. Protected rows and cells remain in private normalized and
EngineeringDocument artifacts.
