# ADR-0013: Preserve page-start and term-definition clause anchors

## Status

Accepted

## Context

The first alignment implementation exposed systematic missing and inferred
alignments for clauses that use document layouts different from conventional
headings.

Two recurring cases were identified in EN 50716:

1. Numbered clauses without a dedicated heading, where the clause reference
   and the first sentence share the same text item.
2. Terms and definitions, where the clause reference and the term are rendered
   on separate lines. Several of these references occur as the first content
   item on a page.

The normalization stage previously generalized digits in repeated page-element
signatures. Multi-level clause references at the top of several pages could
therefore appear structurally similar to page headers. A reference-only text
item was also not accepted as a candidate unless it was classified as a
heading.

AtlasData cannot be used to decide whether the remainder following a reference
is an original heading. For copyright reasons, AtlasData may contain generated
headings for clauses whose source document contains no heading.

## Decision

We preserve syntactically recognizable multi-level clause references throughout
normalization and extend reference candidate detection for source-observed
layout variants.

### Normalization

A text item matching a multi-level numeric or annex reference, for example
`3.1.15`, `A.1`, or `ZA.2`, is protected from:

- repeated header or footer suppression;
- page-number suppression;
- numeric page-signature generalization; and
- text-fragment merging with the following item.

Suppressed page elements retain their observed text and page number for later
diagnostics.

### Reference candidate detection

A reference-only `NormalizedText` or `NormalizedHeading` is a valid candidate.
It does not require an inline title or content remainder.

When a reference-only item is followed immediately by a short text or heading
item that does not itself begin with a reference, that item is recorded as a
following label. This supports terms-and-definitions layouts such as:

```text
3.1.15
availability
ability of an item ...
```

The detector classifies inline remainders from source structure only:

- remainder in a heading item: `title`;
- remainder in a text item: `content`;
- no inline remainder: `unknown`.

AtlasData titles do not determine this classification because they may be
generated rather than source-observed.

### Alignment

Alignment preserves the observed remainder kind and following label. Title
similarity and title-mismatch diagnostics are applied only to remainders
classified as source-observed titles. Inline clause content is never compared
against a generated AtlasData heading.

## Consequences

### Positive

- Clause references at page starts are no longer lost as repeated headers.
- Reference-only term-and-definition anchors can align exactly.
- Inline clauses without dedicated headings are represented correctly.
- Generated AtlasData headings no longer distort source-layout interpretation.
- Future content enrichment can split references, labels, and inline content
  without reparsing the source document.
- Suppression decisions become easier to diagnose.

### Negative

- Candidate and alignment schemas gain additional fields and schema versions.
- Following-label detection remains heuristic and deliberately conservative.
- A syntactically valid clause-like string may still require later alignment
  context to distinguish it from unrelated content.

## Alternatives considered

### Infer missing clauses from neighboring anchors

Rejected as the primary solution. Sequence inference hides missing source
anchors and produces weaker clause boundaries.

### Use AtlasData titles to classify source remainders

Rejected because AtlasData headings may be generated and do not necessarily
reflect the original PDF layout.

### Disable repeated header detection for all numeric items

Rejected because genuine page numbers and numeric page furniture still need to
be removed. Protection is limited to multi-level clause-reference patterns.

## Follow-up

Re-run normalization, reference detection, and alignment for EN 50716 and
compare:

- exact matches for clauses in sections 1 and 4;
- exact matches for page-start terms in section 3.1;
- remaining missing and inferred alignments;
- suppressed-item diagnostics at affected pages.
