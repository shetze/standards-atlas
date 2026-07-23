# ADR-0028: Deterministic Page Furniture Classification

## Status

Accepted

## Context

ADR-0027 requires the pipeline to preserve extractor observations separately
from normalized interpretation. The EN 50126-1:2017 Docling export demonstrates
why this separation is necessary: the repeated page heading
`EN 50126-1:2017 (E)` occurs 101 times, but Docling classifies the occurrences
inconsistently as `page_header`, `section_header`, and ordinary `text`.

A normalization rule which trusts only the extractor label therefore leaks
page furniture into the document body. A rule which suppresses every repeated
text is also unsafe because standards legitimately repeat requirements,
headings, table labels, and clause references in the body.

Page-furniture suppression must consequently be based on combined evidence and
must produce an auditable decision rather than silently changing the extractor
observation.

## Decision

The normalization application layer shall use a deterministic
`PageFurnitureClassifier` before active-content normalization.

The classifier shall consider textual items independently of their Docling
semantic label. It groups equivalent text by a normalized signature and
classifies an occurrence as page furniture only when all required evidence is
present:

- the signature occurs on at least the configured minimum number of distinct
  pages;
- at least 80 percent of the occurrences have usable page-relative geometry;
- their positions form a compact cluster; and
- the cluster lies within the top or bottom 12 percent of the page.

Coordinates shall be interpreted relative to the preserved page height and
shall support both top-left and bottom-left coordinate systems.

Repeated items which Docling consistently labels as `page_header` or
`page_footer` remain supported as a compatibility path, including older
fixtures without page dimensions. A unique explicit header or footer is not
suppressed merely because of its label.

Page-number patterns are classified independently. Clause-like anchors are
protected from repeated-margin classification, even when they occur near a
page boundary.

Every positive classification shall produce an immutable
`PageFurnitureDecision` containing:

- source item identity;
- interpreted role;
- rule identifier;
- confidence;
- original text and Docling label;
- page number;
- normalized signature;
- occurrence and distinct-page counts; and
- median relative margin position where available.

The source item and its original observations remain unchanged. Normalization
uses the decision to place the item in `suppressed_items` and records both the
suppression and the classification decision in the persisted
`NormalizedDocument`.

The `NormalizedDocument` schema version is raised to 5.

## Rules

The initial deterministic rule set is:

1. `page-number-pattern`
   classifies isolated page-number forms.
2. `repeated-margin-text`
   classifies repeated text in a compact top or bottom page-relative position
   cluster.
3. Consistent native `page_header` and `page_footer` labels are accepted only
   when the text repeats across the configured minimum number of pages.
4. Clause anchors matching the protected clause syntax are never classified by
   the repeated-margin rule.
5. Repetition without margin evidence is insufficient.

The existing `suppress_repeated_page_elements` option remains as a legacy
fallback for extracted artifacts which have bounding boxes but no preserved
page dimensions. New Docling artifacts shall use the page-relative classifier.

## Invariants

1. Classification is deterministic for the same extracted document and
   options.
2. Docling labels are observations, not authoritative semantic decisions.
3. Body repetition alone never causes suppression.
4. Every classifier-based suppression has a corresponding auditable decision.
5. Page dimensions are never fabricated when absent.
6. Classification does not mutate source evidence or layout evidence.

## Consequences

### Positive

- Systematically mislabelled EN 50126-1 page headings no longer enter the
  Markdown body.
- Classification remains robust across different page sizes and coordinate
  origins.
- False positives are reduced by requiring both repetition and page-relative
  position.
- Every correction can be inspected and qualified independently of Docling.
- The classifier becomes a reusable deterministic service for future document
  families.

### Negative

- Documents without page dimensions cannot benefit from the strongest rule and
  may require the compatibility fallback.
- The 12 percent margin and 80 percent evidence thresholds are policy values
  which may require controlled evolution against a qualification corpus.
- Some legitimate repeated running headings may be suppressed even when they
  carry contextual value; the original observations remain available for
  alternate exports.
- Persisted normalized artifacts grow because decisions are retained.

## Verification

The rule set shall be covered by tests for:

- mixed Docling labels at a repeated top-margin position;
- top-left and bottom-left coordinates;
- repeated body text;
- protected clause anchors;
- repeated footers;
- unique explicit headers; and
- deterministic persisted decisions.

The EN 50126-1 Docling artifact is a qualification example: all 101 occurrences
of `EN 50126-1:2017 (E)` shall be interpreted as page headers while preserving
their original mixed labels.

## Follow-up

The next slices shall add:

1. a visual asset and formula contract;
2. hierarchical list reconstruction; and
3. a transformation ledger which can reference page-furniture decisions.
