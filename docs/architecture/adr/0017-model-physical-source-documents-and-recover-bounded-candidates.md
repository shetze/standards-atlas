# ADR 0017: Model physical source documents and recover bounded reference candidates

## Status

Accepted

## Context

Standards Atlas imports logical standards collections from AtlasData, while PDF
extraction frequently operates on one physical part of a multi-part standard.
For example, AtlasData persists the complete ISO 26262 series as `ISO26262`, but
Docling converts the physical Part 8 PDF under `ISO26262-8`. Pipeline keys that
implicitly require both artifacts to have identical scope cannot represent this
relationship correctly.

Clause starts also have two legitimate source forms. Many clauses have a visible
heading, while others start with only the clause number followed immediately by
copyrighted normative text. AtlasData may contain a generated public heading for
the latter, but that heading does not occur in the PDF. Candidate detection can
still identify the inline clause number with lower confidence. A greedy monotone
alignment may leave such a candidate unused when duplicate or stronger heading
candidates influence the earlier selection.

## Decision

The processing key always denotes the scope of the physical source document.
A logical aggregate such as `ISO26262` remains the imported master engineering
document. A physical part such as `ISO26262-8` is represented by a deterministic,
derived engineering-document view whose clauses are selected from the master and
whose provenance records the parent document.

Automatic alignment retains its primary monotone selection of strong candidates.
After that pass, it performs bounded low-confidence recovery for missing clauses:

- only candidates already mapped to the expected AtlasData clause are considered;
- a candidate must lie after the preceding aligned clause and before the following
  aligned clause;
- established alignment anchors are never displaced or reordered;
- a recovered clause receives the explicit `low_confidence` status and a
  `LOW_CONFIDENCE_REFERENCE` diagnostic;
- full-document Markdown review marks the location with a private HTML comment.

Low-confidence alignments are valid automatic alignment points. They allow the
pipeline to continue without mandatory human review, while remaining visible and
reviewable. Human review may remove or replace them through the existing marker
workflow.

## Consequences

Multi-part standards no longer require Docling artifacts for unrelated parts to
share one directory or one physical-document key. A dedicated derivation command
or application service must create part-scoped engineering documents from their
logical master documents.

Inline clause-number candidates can close otherwise missing alignment gaps without
inventing copyrighted headings or copying clause content into version-controlled
artifacts. Alignment statistics distinguish low-confidence recovery from exact,
normalized, annex, sequence-inferred and manual decisions.

The recovery pass is intentionally conservative. It cannot resolve candidates
outside established neighbouring anchors or ambiguity in the expected engineering
structure; those cases remain missing and available for human review.
