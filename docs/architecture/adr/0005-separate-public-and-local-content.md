# ADR 0005 – Separate Public and Local Document Content

## Status

Accepted

## Context

Standards Atlas maintains engineering knowledge from multiple sources.

The public AtlasData repository is published under an open-source license
and therefore must never contain copyrighted text originating from
commercial standards unless explicit permission has been obtained.

Currently, AtlasData contains only the manually maintained document
structure and generated TOC records. During document processing,
however, the canonical `EngineeringDocument` may contain the complete
clause text extracted from internal sources such as Markdown
conversions, PDFs, or other engineering repositories.

This internal working representation is required for semantic analysis,
document transformations, AI-assisted processing, and future
traceability features.

The AtlasData round-trip workflow must therefore guarantee that
copyright-protected text can never accidentally be written back into
the public repository.

The canonical EngineeringDocument may contain multiple annotations for each
clause. Export adapters decide which annotations are eligible for publication.

## Decision

Standards Atlas distinguishes explicitly between **public** and
**local/internal** document content.

The canonical `EngineeringDocument` may contain complete clause text as
its internal working representation.

AtlasData, however, only stores content that is explicitly intended for
publication.

Initialization records are therefore divided into separate categories.

### TOC

Stores publicly distributable clause headings.

The project has explicit permission to distribute these headings.

### PublicTXT

Stores publicly distributable annotations or explanatory text.

This content is authored specifically for publication and may be
included in the public AtlasData repository.

### LocalTXT

Represents local or organisation-specific annotations.

LocalTXT records are never written into the public AtlasData repository.

### Clause Text

The `Clause.text` property belongs to the internal intermediate
representation.

Its content may originate from copyrighted standards or other internal
sources.

It must never be exported automatically to AtlasData.

## AtlasData Round-Trip

The AtlasData round-trip writer only writes:

- TOC
- PublicTXT

It never writes:

- LocalTXT
- Clause.text
- any other internally derived document text

Existing LocalTXT records are ignored by the public writer.

## Transformation Pipeline

Transformations operate exclusively on the canonical
`EngineeringDocument`.

They may freely use the complete internal clause text for analysis,
validation, semantic enrichment, AI-assisted processing, or traceability
generation.

Export adapters are responsible for deciding which information is
allowed to leave the internal representation.

## Consequences

### Positive

- Prevents accidental publication of copyrighted standard text.
- Clearly separates public knowledge from internal working data.
- Enables rich semantic processing without legal risk.
- Allows publication-quality annotations to coexist with internal notes.
- Makes export policies explicit and testable.

### Negative

- Export adapters require explicit visibility handling.
- Multiple representations of annotations may exist.
- Public and local annotations may diverge over time.

## Alternatives Considered

### Store all text in AtlasData

Rejected because copyrighted content could accidentally be committed to
the public repository.

### Remove Clause.text from the domain model

Rejected because semantic transformations, validation, and AI-assisted
processing require access to the complete document content.

### Separate public and local repositories only

Rejected because visibility is a property of the content itself rather
than the storage location.

Explicit visibility within the data model provides stronger guarantees
and simplifies future export adapters.

## Decision Outcome

Standards Atlas treats the canonical `EngineeringDocument` as the
complete internal representation of engineering knowledge.

Public AtlasData files contain only explicitly publishable information.

The distinction between internal and public content is enforced by the
export adapters rather than by the transformation pipeline.
