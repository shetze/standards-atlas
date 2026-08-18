# ADR 0055: Preserve visual formulas before semantic transcription

## Status

Accepted

## Context

Docling can identify mathematical formula items and provide page-level source evidence even
when it cannot produce a reliable semantic transcription. Standards Atlas previously
represented those items as `visual_only` formulas with an empty or diagnostic expression
and rendered the message `semantic transcription unavailable` in Markdown. The actual
formula image was therefore not carried into the canonical `EngineeringDocument` even
though the source page and bounding box were known.

This is undesirable for engineering standards. Mathematical expressions may define
calculations, thresholds, transformations, or algorithms that are valuable for later
machine processing. Losing the visual representation also prevents a later multimodal
transcription step from operating on the preserved engineering artifact.

## Decision

Preserve the visual representation of every already-identified `visual_only` formula when
usable PDF source evidence is available.

Docling remains the primary formula-discovery adapter. A separate PyMuPDF-backed adapter
must not search for formulas or infer new formula regions. It receives the source PDF and
the page/bounding-box evidence already produced by Docling and deterministically renders a
PNG crop with configurable DPI and padding.

The generated visual payload is represented through the existing adapter-neutral
`VisualAsset` contract and propagated along the canonical path:

```text
ExtractedFormula
    -> NormalizedFormula
    -> FormulaBlock
    -> Markdown / later enrichment adapters
```

`FormulaBlock` retains formula semantics as its content type. A visual-only formula is not
converted into a `PictureBlock`. The block may therefore carry both its formula status and
an embedded or materialized image asset.

For persisted Docling workflows, `DoclingExtractedDocumentRepository` decorates the
adapter-neutral extracted document with formula visuals when the conversion metadata still
points to an accessible source PDF. If the source path or geometric evidence is not
available, the formula remains `visual_only` without an image; no location is guessed.

Markdown publication materializes embedded formula assets beside other visual assets and
renders the image together with the existing `semantic transcription unavailable` status.
For `visual_only` formulas, diagnostic pseudo-expressions emitted by Docling are not copied
into the canonical `EngineeringDocument` and are not rendered in Markdown. The source PNG
and status caption remain the fallback representation until semantic transcription succeeds.
This preserves the distinction between a visual source representation and a verified
semantic transcription.

## Consequences

- Formula imagery is no longer discarded merely because semantic transcription failed.
- Normalization remains deterministic and does not require an LLM.
- Formula identity and source evidence remain attached to a `FormulaBlock`, avoiding a
  lossy detour through generic pictures.
- PyMuPDF is a regular runtime dependency because formula visual preservation is part of the standard normalization path; Docling itself remains optional.
- Engineering-document JSON may temporarily contain embedded base64 image data, matching
  the existing picture-asset approach; publication materializes those assets as files.
- Later formula transcription can operate as a separate enrichment stage without changing
  the extraction or normalization contract.
- Re-running a later transcription model does not require re-detecting formula locations.

## Alternatives considered

### Treat formulas as pictures

Rejected because the system already knows that these regions are formulas. Converting them
to `PictureBlock` values would discard semantic type information that later stages would
have to reconstruct.

### Perform formula recognition during normalization

Rejected because normalization is deterministic and model-independent. Formula
transcription belongs to a separate enrichment stage with its own provenance and review
policy.

### Generate MathML directly during extraction

Deferred. MathML, LaTeX, OpenMath, or a mathematical AST may be useful semantic
representations, but Slice 1 only guarantees preservation of the visual source. Choosing
and validating a canonical transcription format is a separate architectural decision.

## Amends

- ADR 0008: Use Docling as the PDF extraction adapter
- ADR 0016: Require lossless extracted-document normalization
- ADR 0029: Define visual content and caption ownership
- ADR 0033: Establish the engineering-document construction contract
