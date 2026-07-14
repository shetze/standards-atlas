# ADR-0016: Require lossless extracted-document normalization

## Status

Accepted

## Context

The normalization stage transforms the adapter-neutral `ExtractedDocument` into a
`NormalizedExtractedDocument`. During review of EN 50716, valid clause content at
the top and bottom of pages 21 and 22 disappeared even though it was present in
the native Docling document. The affected elements had been classified near page
boundaries and were removed by page-header/page-footer suppression or lost during
subsequent transformations.

The review and alignment stages cannot recover content that has already
vanished from the normalized representation. Human review is intended to correct
semantic alignment, not to transcribe copyrighted source text from the PDF.

## Decision

Normalization SHALL be provenance-preserving and lossless with respect to
extracted source items.

Every `ExtractedItem.id` must occur exactly once in one of these locations:

1. `source_item_ids` of an active normalized item; or
2. `source_item_id` of a `SuppressedItem`.

After all normalization phases, the normalizer performs source-item accounting.
Missing or duplicate source IDs raise `NormalizationDataLossError` by default.
Statistics expose active, suppressed, unaccounted, and duplicate source-item
counts.

Page-boundary handling becomes conservative:

- Pure page numbers may still be suppressed.
- Explicit Docling `page_header` and `page_footer` items are suppressed only when
  their normalized signature repeats at least the configured minimum number of
  times.
- Unique items marked as header or footer remain active because Docling labels
  can be wrong.
- Unlabelled repeated page elements are not suppressed by default. The previous
  heuristic can be enabled explicitly with
  `suppress_repeated_page_elements=true`.
- Items beginning with a multi-level numeric or supported annex reference are
  protected from page-element suppression.

Merge and list transformations must preserve the original extracted IDs rather
than substituting normalized-item IDs.

## Consequences

- Real content at page boundaries is retained unless there is strong repetition
  evidence that it is page furniture.
- Some headers or footers may temporarily remain in the active normalized
  sequence. This is preferable to losing normative content and can be handled by
  later structural review.
- A normalization run fails early if a future transformation silently drops or
  duplicates source items.
- Existing normalized artifacts must be regenerated because the metadata schema
  and default suppression behavior changed.
- Downstream candidate, alignment, and review artifacts must also be regenerated.
