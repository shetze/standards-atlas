# ADR-0029: Visual Content Contract and Caption Ownership

## Status

Accepted

## Date

2026-07-23

## Context

The EN 50126-1 regression comparison exposed two related problems. First, captions referenced by Docling tables were imported both as independent body text and as the table caption. Markdown consequently rendered every affected table caption twice. Picture captions improved after layout evidence preservation because referenced caption text became available on the picture item, and that improvement must not be lost.

Second, the canonical pipeline treated pictures mainly as opaque Docling references and formulas as plain strings. Docling already embeds raster payloads for many pictures, while some formula objects contain no verified semantic text and only an `orig` transcription plus page geometry. Discarding these distinctions either loses information or presents an unreliable transcription as verified mathematics.

## Decision

A caption referenced by a table or picture is owned by that visual item. It is retained in the visual item's caption and layout evidence, but it is not emitted a second time as independent body content.

Introduce a visual-content contract across extraction, normalization and engineering content:

- `VisualAsset` preserves media type, SHA-256 content identity, embedded data URI and intrinsic dimensions.
- Pictures carry the visual asset through `ExtractedPicture`, `NormalizedPicture` and `PictureBlock`.
- Markdown file export materializes embedded assets under an adjacent `assets/` directory using the content hash as filename and emits a relative image link.
- Formula items preserve both the selected expression and Docling's original expression.
- Formula extraction status is explicit: `visual_only`, `machine_extracted` or `human_verified`.
- A formula without verified semantic text is rendered as an explicit visual-only placeholder and is never formatted as verified LaTeX or mathematical text.

The deterministic normalized payload schema is raised to version 6.

## Invariants

1. A referenced caption appears exactly once in the logical reading stream.
2. Caption ownership does not remove the original reference from layout evidence.
3. Identical embedded visual bytes produce the same asset hash and filename.
4. Exporting an EngineeringDocument does not require Docling to be installed.
5. A `visual_only` formula must be distinguishable from a semantically extracted formula in every downstream representation.
6. Missing semantic formula extraction is not silently treated as successful extraction.

## Consequences

Markdown exports now include an `assets/` directory when embedded pictures are present. EngineeringDocument JSON becomes larger because embedded data URIs remain available until export; a later asset repository may externalize them while retaining the same hash-based contract.

Formula images are not yet cropped from the source PDF. The preserved page and bounding-box evidence provides the deterministic locator required for that later step. Until a rendered crop or verified semantic representation exists, Markdown communicates the limitation explicitly.

## Follow-up

- Add source-PDF crop generation for `visual_only` formulas.
- Classify decorative images, logos and substantive figures separately.
- Externalize visual payloads into a workspace asset repository without changing their content identity.
- Add figure/table cross-reference resolution in EngineeringDocument construction.
