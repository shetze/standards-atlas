# ADR 0085: Use manifest-driven family AtlasData onboarding

## Status

Accepted.

## Context

Docling produces one `document.json` per physical source document, while legacy AtlasData
represents a multipart standard family in one public structural file. The existing
`atlasdata onboard-docling-parts` command can compose several physical parts, but requires
callers to repeat every `PART=PATH` association manually. That duplicates information already
declared by the standards manifest and makes large families such as IEC 61508 cumbersome to
onboard consistently.

Multipart families can also contain parts from different publication years. IEC 61508 uses a
2005 introductory part and 2010 normative parts, so projecting the family-level year onto every
physical part loses source identity.

## Decision

Add `atlasdata onboard-family FAMILY --manifest ...` as the manifest-driven onboarding entry
point. The CLI resolves physical part keys, publication years, and expected Docling artifact
paths from the standards catalog and delegates all structural discovery to the existing
`AtlasDataOnboardingService.generate_parts()` implementation.

`onboard-docling` remains the single-document diagnostic path and `onboard-docling-parts`
remains available for explicit/manual composition. The family command does not introduce a
second Docling parser.

Part definitions may declare an optional `publication_year`. When absent, the family year is
the fallback. AtlasData structure lines and public references use the resolved year of each
physical part. Supplements are separate documents by default and are included only when
`--include-supplements` is requested.

Generated family baselines default to `local/proposed/<family>` so a reviewed or published
AtlasData baseline is never overwritten implicitly.

## Consequences

- Family onboarding has one manifest-controlled source of part identity and ordering.
- Mixed-year families retain correct physical provenance in one AtlasData file.
- Existing single-part and explicit multipart onboarding remain backward compatible.
- Annex, table, and List-of-Tables improvements can be implemented once in the shared part
  discovery path and immediately benefit family onboarding.
- Part publication years become catalog data when they differ from the family baseline year.
