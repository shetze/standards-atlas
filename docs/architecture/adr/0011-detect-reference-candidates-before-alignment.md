# ADR 0011: Detect clause-reference candidates before document alignment

## Status

Accepted

## Context

The normalized extracted document contains a provenance-preserving sequence of headings, text blocks, lists, tables, pictures, formulas, code, and unknown elements. AtlasData independently provides the expected clause references and stable clause identifiers of the engineering document.

Directly aligning every normalized item with a clause would combine lexical recognition, structural validation, sequence reasoning, and content assignment in one opaque step. Numbers in standards also occur in prose, tables, measurements, dates, and cross-references, so a regular expression alone is not sufficient evidence for a clause boundary.

## Decision

Standards Atlas introduces a separate deterministic reference-candidate detection stage before alignment.

The detector:

- examines only headings and text starts;
- recognizes numeric references such as `6`, `6.4`, and `6.4.2`;
- recognizes alphabetic annex references such as `A`, `A.1`, `ZA`, and `ZZ.2`;
- recognizes explicit forms such as `Annex A`;
- normalizes whitespace and trailing punctuation in references;
- validates every candidate against references in the persisted `EngineeringDocument`;
- preserves unexpected and ambiguous candidates as diagnostics instead of discarding them;
- records the remaining heading text as a possible title without changing the canonical clause title;
- persists results exclusively below `.atlas/reference-candidates/`.

The stage produces a `ReferenceCandidateDocument`. It does not modify the normalized document or the engineering document, and it does not yet determine clause content ranges.

## Consequences

Reference detection can be tested and inspected independently from sequence alignment. AtlasData constrains false-positive recognition while still allowing deviations in the PDF to remain visible. The following alignment slice can use candidates, confidence, status, sequence numbers, and expected clause identifiers as explicit input.

Potential references embedded later in prose are deliberately excluded in this slice because they are more likely to be cross-references than clause starts. Special sections such as bibliography and indexes may be added later as explicit structural candidate types.
