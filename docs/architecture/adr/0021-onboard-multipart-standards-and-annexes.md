# ADR 0021: Onboard multi-part standards and annexes from Docling documents

## Status

Accepted

## Context

A standard family can be published as several independently numbered parts. Each part is converted by Docling into a separate JSON document, while the established AtlasData format represents the complete family in one file. Clause references such as `1`, `3.1` or `A.1` are therefore only unique together with their part context.

Annexes use visible letter references but AtlasData stores them behind a numeric structural anchor, for example `1-42:A`. The visible engineering reference remains `A` or `A.1`.

Docling does not always emit an annex heading before its subclauses. In the IEC 11889 conversion, `A.1` can occur before the separate `Annex A` heading. Source order alone is therefore not a reliable hierarchy.

## Decision

The onboarding service accepts an explicit sequence of `DoclingPartSource(part, path)` values. The CLI exposes this as repeated `--part PART=PATH` options through `atlasdata onboard-docling-parts`.

The service:

1. rejects duplicate part assignments;
2. sorts parts numerically;
3. processes each Docling document independently;
4. produces one AtlasData `structure` line per part;
5. prefixes structure tokens with the part number;
6. includes the part in generated TOC references and hashes;
7. keeps clause references unique only inside their part.

Annex headings are recognized in these forms:

- `Annex A`
- `Annex A (normative)`
- `Annex A (informative) Title`
- `A.1 Title`

Discovered annex references are reordered into canonical pre-order by annex letter and numeric suffix. Each annex receives a numeric structural anchor immediately after the highest numeric top-level clause. For example, when the last numeric clause is `41`, Annex A is rendered as `42:A`, Annex B as `43:B`, and so on.

Normative or informative status is retained in the public annex heading. It is not encoded as a new legacy type marker because AtlasData has no established marker for this distinction.

The existing single-document `generate()` API remains backward compatible and delegates to the multi-part implementation without adding a visible part context.

## Consequences

- One AtlasData file can be generated from several Docling JSON files.
- Repeated clause numbers in different parts no longer collide in hashes or output references.
- Annexes and annex subclauses participate in normalization and alignment using their visible letter references.
- Generated output remains compatible with existing AtlasData readers.
- Docling heading omissions remain visible as gaps in the generated skeleton and require review before replacing curated AtlasData.
