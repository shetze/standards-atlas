# ADR 0008: Use Docling as the PDF extraction adapter

- Status: Accepted
- Date: 2026-07-13

## Context

Engineering standards are normally available as PDF documents. PDF preserves visual layout, but it does not provide the reliable semantic clause structure required by Standards Atlas. Exporting PDF directly to Markdown would make a lossy presentation format part of the processing core and would discard useful layout and provenance information before semantic alignment can take place.

Standards Atlas already imports the expected standard structure from AtlasData into the canonical `EngineeringDocument`. It also provides structured clause content blocks and adapter-neutral source evidence. Potentially copyrighted standard content must remain outside the public Git repository and is stored below the ignored `.atlas` workspace.

Docling provides a unified document representation for extracted PDF content, including reading order, text, tables, pictures, formulas, pages and bounding boxes. Its native model is nevertheless an external adapter model and must not become part of the Standards Atlas domain.

## Decision

Docling is introduced as an optional PDF extraction adapter.

The processing stages are separated as follows:

```text
PDF
  -> native DoclingDocument
  -> adapter-neutral ExtractedDocument
  -> later semantic alignment
  -> enriched EngineeringDocument
```

The native Docling document is serialized losslessly as JSON below:

```text
.atlas/docling/<document-key>/document.json
```

Reproducibility metadata, including the source path, source hash and converter version, is stored separately in:

```text
.atlas/docling/<document-key>/conversion.json
```

Docling is an optional dependency. The core package, AtlasData import, persistence and existing exporters remain usable without installing Docling. The adapter imports the Docling runtime lazily only when PDF conversion is requested.

Application and domain code do not receive `DoclingDocument` instances. Persisted native Docling JSON is mapped into an adapter-neutral `ExtractedDocument` containing ordered text, heading, list, table, picture and formula observations with neutral `SourceEvidence` objects.

The raw Docling JSON is not modified during semantic correction. Future alignment results update and enrich the canonical `EngineeringDocument` while retaining separate audit and diagnostic artefacts.

Markdown remains an export representation and is not used as an intermediate canonical format.

## Consequences

### Positive

- Full Docling extraction information remains available for later alignment improvements.
- Expensive PDF conversion does not need to be repeated when alignment logic changes.
- The domain remains independent of Docling and its release cycle.
- Stored extraction results can be inspected without loading the Docling runtime.
- Protected standard content remains below `.atlas` and outside Git.
- Source hashes make stale extraction results detectable.
- The adapter can later be replaced or complemented by other extraction technologies.

### Negative

- An additional adapter-neutral extraction model must be maintained.
- Native Docling JSON and the canonical `EngineeringDocument` coexist as separate private artefacts.
- Docling is a large optional dependency and may require platform-specific runtime packages or models.
- Mapping must tolerate compatible changes in Docling's serialized schema.

## Scope of version 0.5

Version 0.5 includes:

- optional Docling dependency,
- PDF-to-native-JSON conversion,
- private workspace persistence,
- source hashing and conversion metadata,
- adapter-neutral extraction models,
- native JSON reading and inspection,
- CLI commands for conversion and inspection,
- unit tests based on an artificial, copyright-free fixture.

Semantic clause alignment and enrichment of the `EngineeringDocument` are prepared by this decision but remain a separate implementation step.
