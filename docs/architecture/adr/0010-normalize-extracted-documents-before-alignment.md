# ADR 0010: Normalize extracted documents before semantic alignment

## Status

Accepted

## Date

2026-07-13

## Context

The Docling adapter produces a faithful, adapter-neutral `ExtractedDocument` from a native
`DoclingDocument`. The extracted sequence still contains representation artefacts that are
appropriate for PDF extraction but unsuitable for direct semantic alignment. Typical examples
are repeated page headers and footers, variable page numbers, decomposed Unicode, non-breaking
spaces, line and page hyphenation, fragmented paragraphs, and partially recognized lists.

Changing the native Docling artefact or mutating the `ExtractedDocument` would make extraction
results difficult to audit and would mix adapter responsibilities with application logic.
Semantic alignment also requires every transformation to retain traceability to the originating
PDF items.

Docling additionally identifies preformatted content with the label `code`. Treating this as
ordinary prose would destroy meaningful indentation and line breaks.

## Decision

Standards Atlas introduces a separate deterministic normalization stage:

```text
DoclingDocument
    -> ExtractedDocument
    -> NormalizedExtractedDocument
    -> future structural analysis and semantic alignment
```

The source `ExtractedDocument` remains unchanged. Normalization is implemented in the application
layer and has no dependency on Docling.

`NormalizedExtractedDocument` contains an ordered sequence of normalized item types. Each item
records all source item identifiers and all source evidence that contributed to it. Suppressed
page elements are retained as explicit `SuppressedItem` records rather than being silently
deleted.

The initial normalization pipeline performs the following deterministic operations:

1. Unicode normalization using NFC by default.
2. Conservative prose whitespace normalization.
3. Suppression of explicit or repeatedly observed headers, footers, and page numbers.
4. Conservative repair of word hyphenation within and across text items.
5. Rule-based merging of adjacent prose fragments.
6. Consolidation and reconstruction of lists when at least two compatible list markers occur.
7. Preservation of tables, pictures, formulas, and unknown elements without structural loss.

The pipeline introduces three code representations:

```text
Docling label "code" -> ExtractedCode -> NormalizedCode -> CodeBlock
```

Code normalization is intentionally conservative. It applies Unicode normalization, normalizes
line endings, and removes unsupported control characters, but preserves indentation, repeated
spaces, and line breaks. Code is excluded from prose whitespace, hyphenation, list, and fragment
merging rules.

Normalized documents are versioned and stored exclusively below:

```text
.atlas/normalized/<document-key>/document.json
```

The persisted metadata contains the source extraction hash, normalizer version, options,
timestamp, and transformation statistics. A normalized artefact is considered current only when
its source hash, options, and normalizer version match the active inputs.

## Consequences

### Positive

- Native Docling artefacts and extracted observations remain auditable and reproducible.
- Alignment receives a cleaner and more stable input representation.
- Every merge and suppression remains traceable to the original PDF evidence.
- Normalization can be tested without Docling or copyrighted source documents.
- Code formatting is preserved from extraction through the canonical content model.
- Different normalization strategies can later be compared without rerunning PDF extraction.

### Negative

- A third persisted document representation is introduced.
- Header/footer and fragment heuristics can produce false positives and require diagnostics and
  future tuning against real standards.
- Normalization schema and algorithm versions must be managed explicitly.

## Rejected alternatives

### Normalize native Docling JSON in place

Rejected because it would destroy the original extraction evidence and couple Standards Atlas to
Docling's internal schema.

### Normalize while reading Docling JSON

Rejected because extraction and normalization would no longer be independently reproducible or
testable.

### Normalize directly into EngineeringDocument clauses

Rejected because clause boundaries are not known before structural analysis and semantic
alignment.

### Treat code as plain text

Rejected because prose normalization would alter indentation, line breaks, and repeated spaces.

## Follow-up

The next slice will detect clause reference candidates and analyze the normalized structural
sequence before aligning it with the AtlasData-derived `EngineeringDocument`.
