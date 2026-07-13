# ADR 0009: Harden the Docling extraction boundary

- Status: Accepted
- Date: 2026-07-13

## Context

ADR 0008 introduced Docling as an optional PDF extraction adapter. The first implementation could convert PDFs, persist native Docling JSON below `.atlas`, and map that JSON into an adapter-neutral `ExtractedDocument`.

Before clause normalization and alignment can rely on this boundary, extraction must be reproducible, diagnosable, safe, and testable with a real PDF. In particular, an existing artifact is not sufficient evidence that it still belongs to the current source file, unknown Docling labels must not disappear silently, and potentially copyrighted content must not be written outside the private workspace.

## Decision

The Docling extraction slice ends at the stable transformation:

```text
PDF -> native Docling JSON -> ExtractedDocument
```

The following rules apply:

1. Every conversion records the source SHA-256 hash, source size, absolute source path, UTC timestamp, Docling version, and effective conversion options.
2. The repository distinguishes missing, current, stale, and incomplete extractions.
3. A current extraction is reused unless overwriting is explicitly requested.
4. A stale or incomplete extraction requires explicit `--overwrite`.
5. Document keys are validated and cannot contain absolute paths or path components.
6. All native extraction artifacts and metadata remain below the configured `.atlas` workspace.
7. Unknown Docling labels are represented as `ExtractedUnknown`; they are never discarded silently.
8. Extraction inspection reports page coverage, supported item counts, unknown item counts, and unknown labels.
9. Unit tests use synthetic JSON fixtures. A separately marked integration test converts a self-authored PDF with the installed Docling runtime.
10. Text normalization, header/footer removal, clause reference detection, and semantic alignment are explicitly deferred to later application services.

## Consequences

The extraction boundary becomes reproducible and suitable as input for deterministic normalization and alignment. Source changes are visible before an outdated extraction can be used. New Docling item labels remain observable even before a dedicated mapping exists.

The metadata includes an absolute source path. It is stored only below `.atlas` and must not be committed. Moving the source file does not make the extraction stale; the content hash remains authoritative.

The real integration test can be slower and may require locally cached Docling model artifacts. It is therefore marked `docling` and can be run separately from the normal unit suite.
