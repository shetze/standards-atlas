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

### Review table captions in the last field

`TABLE` records place generated parent metadata before the HITL caption:

```text
TABLE;<hash>;IEC 61508-1:2010 Table 1;7.1.2.2;
TABLE;<hash>;IEC 61508-1:2010 Table 1;7.1.2.2;Reviewed public caption
```

The first line is an empty-caption example; replace it with the reviewed line,
not an additional duplicate. Field 4 is the containing clause reference; field
5 is the caption. `TOC` and `TABLEINDEX` field ordering is unchanged.

Existing ordinary `TABLE;hash;reference;caption;parent` records are accepted on
import. `generate-toc --write` rewrites them in the new order, retaining reviewed
captions and parents. Keep the generated `# table-record-layout: parent-caption`
comment: it prevents reference-shaped captions such as `A.2` from being mistaken
for parent references. For an unmarked legacy file with reference-shaped captions,
declare `# table-record-layout: caption-parent` in the data section before the
first migration; see the [format specification](../reference/atlas-data-format.md).

This field-order change alone does not change table IDs, hashes or canonical
document data, and does not require rerunning Docling or LLM enrichment. A pure
layout migration creates one numbered backup; subsequent unchanged writes are
idempotent. The distinct numbering migration below may change table identities.

Index `0` denotes a table without caption and without a List-of-Tables entry.
Keep its `b` token and parent association for normalization/alignment. Its
`TABLE` record may have an empty fifth field; do not add a placeholder caption
or a `TABLEINDEX` just to fill it. The field swap neither removes these
structural declarations nor changes the alignment algorithm.

### Refresh table numbering from `b` declarations

The structural token `1-b7.1.2.2.1` identifies `Table 1` in part 1, located in
clause `7.1.2.2`; `2-b9:A.3.15` identifies `Table A.15` in part 2, located in
clause `A.3`. Keep these structure paths: they support parent assignment while
the public table labels are generated independently.

Preview and write the corrected records with:

```bash
uv run standards-atlas atlasdata generate-toc data/IEC61508
uv run standards-atlas atlasdata generate-toc data/IEC61508 --write
```

The write operation creates a numbered backup when the file changes. Existing
legacy `TABLE` and `TABLEINDEX` references are migrated through their matching
`b` declarations, preserving captions and explicit parent metadata. Already
canonical and legacy aliases are merged into one table per identity. Standalone
records without a matching declaration remain unchanged; they may need manual
review, especially in family files where no physical part was specified.

Reimport affected EngineeringDocuments before rebuilding their downstream
content/table artifacts. Corrected table labels imply corrected table IDs and
record hashes; existing persisted documents are not rewritten by `generate-toc`
alone. Clause references, clause IDs and the `b` structure declarations do not
change. This operation performs no LLM inference and does not edit enrichment
companions.
