# ADR-0012: Align reference candidates with the AtlasData structure

## Status

Accepted

## Context

The Docling integration now produces three independent private artefacts:

1. the native `DoclingDocument`,
2. a normalized, adapter-neutral document representation, and
3. detected clause-reference candidates.

AtlasData already provides the canonical clause identifiers, visible references,
order and hierarchy. Reference detection alone does not determine which repeated
candidate is the real clause start, whether candidates occur in a valid order,
or which normalized items belong to a clause range.

Writing extracted content directly into `EngineeringDocument` at this stage
would combine uncertain structural decisions with canonical domain data and
would make errors difficult to diagnose or reproduce.

## Decision

Standards Atlas introduces a deterministic alignment stage before canonical
document enrichment.

The alignment engine consumes:

- `EngineeringDocument` as the expected AtlasData-derived structure,
- `NormalizedExtractedDocument` as the ordered observed content, and
- `ReferenceCandidateDocument` as the set of possible clause starts.

It produces a separate `AlignmentResult` containing:

- one `ClauseAlignment` for every expected clause,
- the selected candidate and rejected alternatives,
- explicit or sequence-inferred start positions,
- calculated clause ranges,
- unassigned document ranges,
- structured issues and statistics, and
- hashes of all relevant inputs.

The engine must preserve the expected AtlasData clause order. Candidates that
would violate this order are not silently accepted. Exact candidates are
preferred over weaker matches, while confidence and observed-title similarity
are used to choose between duplicate candidates.

A single missing clause between two aligned neighbours may be inferred only
when a non-empty normalized item range exists between them. Such a result is
marked `sequence_inferred` with lower confidence. Multiple unresolved gaps are
left as `missing`.

Alignment never mutates its inputs and does not yet update `Clause.content`.
That enrichment remains a separate processing stage.

## Persistence

Alignment results may include protected titles and references to extracted
standard content. They are therefore stored only below:

```text
.atlas/alignments/<document-key>/alignment.json
```

An alignment is current only when the following values still match:

- normalized-document hash,
- reference-candidate-document hash,
- AtlasData structure hash,
- alignment implementation version, and
- effective alignment options.

## Consequences

### Positive

- AtlasData remains the canonical source of document structure.
- Candidate selection and range formation are reviewable and reproducible.
- Duplicate, missing, unexpected and out-of-order references remain visible.
- No uncertain extracted content is written into the domain model prematurely.
- Later manual overrides can be introduced without replacing the alignment
  model.
- The enrichment stage receives deterministic clause ranges instead of raw
  heuristics.

### Negative

- A further private artefact must be persisted and versioned.
- Conservative inference leaves some clauses unresolved.
- Title similarity is only a supporting heuristic and cannot resolve all
  duplicate candidates.
- Manual review remains necessary for ambiguous or structurally inconsistent
  documents.

## Alternatives considered

### Assign the first matching candidate

Rejected because tables of contents, cross-references and repeated headings can
produce earlier false positives.

### Align solely by reference text

Rejected because duplicated references and out-of-order extraction require
sequence context.

### Update `EngineeringDocument` during alignment

Rejected because it would combine structural diagnosis with protected-content
enrichment and make reruns less transparent.

### Use an LLM to resolve conflicts

Rejected for this slice because the base alignment must remain deterministic,
local, reproducible and testable. AI-assisted review may later consume the
structured issues.
