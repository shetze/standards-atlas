# Standards Atlas

Standards Atlas is an **Engineering Knowledge Transformation Platform**.

It provides a canonical semantic representation of engineering documents together with deterministic transformation pipelines connecting multiple engineering ecosystems.

Rather than being centred around a particular document format or engineering tool, Standards Atlas is built around a common intermediate representation that enables standards, requirements, safety cases and engineering artefacts to be connected through semantic transformations.

---

# Vision

Engineering knowledge exists in many different forms:

- international standards
- requirements specifications
- safety cases
- architecture descriptions
- engineering reports
- compliance evidence
- project documentation

Although these artefacts often describe the same engineering concepts, they usually exist in isolated engineering tools.

Standards Atlas establishes a canonical semantic representation that allows engineering knowledge to move between multiple engineering ecosystems through deterministic transformation pipelines.

The long-term vision is an **Engineering Knowledge Platform** providing reusable traceability, semantic analysis and AI-assisted engineering workflows.

---

# Core Concepts

## EngineeringDocument

The canonical domain model.

Every external representation is imported into an immutable
`EngineeringDocument`.

The EngineeringDocument is the project's canonical Intermediate Representation (IR).

---

## Clause

Represents one logical clause of the original engineering document.

A Clause contains:

- identifier
- document reference
- clause type
- semantic roles
- original heading
- ordered structured content blocks
- adapter-neutral source evidence

The Clause always represents the original engineering artefact.

---

## ClauseAnnotation

Represents knowledge associated with a clause.

Unlike the Clause itself, annotations are generated or maintained during engineering work.

Examples include

- generated titles
- summaries
- explanations
- rationale
- comments
- examples
- discussions

Multiple annotations may exist for every clause.

---

## Annotation Visibility

Every annotation has an explicit visibility.

```
PUBLIC
LOCAL
PRIVATE
```

Only PUBLIC annotations may be exported into public repositories.

This prevents accidental publication of copyrighted engineering content.

---

# Architecture

Standards Atlas follows a Hexagonal / Clean Architecture.

```
                  Command Line Interface
                            │
                            ▼
                 Application Services
                            │
                            ▼
               Transformation Pipeline
                            │
                            ▼
                 EngineeringDocument
      (Canonical Intermediate Representation)
                            ▲
                            │
                 Repository (.atlas)
                            ▲
                            │
                 Import / Export Ports
                            ▲
                            │
                        Adapters
```

The domain model is completely independent of external file formats and engineering tools.

---

# Transformation Pipeline

The Transformation Pipeline contains all semantic processing.

Typical transformations include

- structure validation
- heading synchronization
- semantic role inference
- annotation generation
- relation generation
- traceability validation
- AI-assisted enrichment

Transformations always operate on the canonical EngineeringDocument.

---

# Workspace

Standards Atlas maintains a local engineering workspace.

```
.atlas/

    documents/
        Canonical EngineeringDocument objects

    docling/
        Native Docling JSON and conversion metadata

    doorstop/
        Generated Doorstop workspaces

    transformations/
        Intermediate transformation results

    warnings/
        Validation reports
```

The workspace contains derived engineering knowledge.

Source documents always remain the authoritative source.

---

# Adapters

Standards Atlas connects engineering ecosystems through dedicated adapters.

Each adapter implements one or more application ports while the domain model remains completely independent of external formats.

## AtlasData Adapter

AtlasData is the primary public exchange format for engineering standards.

### Import

Current capabilities

- metadata import
- structure parsing
- compiler-based structure expansion
- semantic role inference
- EngineeringDocument generation
- import of public annotations

### Round-trip

Current capabilities

- regenerate TOC entries
- preserve manually maintained headings
- preserve public annotations
- numbered safety backups

Only explicitly publishable information is written back.

```
TOC
PublicTXT
```

Copyright protected clause text is never exported.

---

## Doorstop Adapter

Doorstop is the primary engineering export adapter.

### Export

Current capabilities

- deterministic Doorstop identifier generation
- complete clause hierarchy
- complete clause text
- public annotations
- local annotations
- private annotations
- Doorstop reference generation
- Standards Atlas metadata
- Git workspace generation
- validation using Doorstop

Generated Doorstop items contain additional engineering metadata including

- original clause reference
- semantic roles
- deterministic numeric identifiers
- project-specific reference patterns

Doorstop workspaces are generated inside

```
.atlas/doorstop/
```

and therefore may contain private engineering information.

---

## Docling Adapter

Docling is the PDF extraction adapter used to preserve document layout, reading order and provenance before semantic alignment. It is an optional dependency and is imported only when a PDF conversion is requested.

The adapter provides:

- PDF conversion into native Docling JSON
- lossless private persistence below `.atlas/docling/`
- source hashing and converter metadata
- reading of persisted JSON without loading the Docling runtime
- mapping to an adapter-neutral `ExtractedDocument`
- text, heading, list, table, picture and formula observations
- page and bounding-box source evidence

Docling does not define the canonical engineering structure. AtlasData remains authoritative for document identifiers, clause references and hierarchy. A subsequent alignment step will assign extracted observations to the existing clauses.

```text
PDF
  -> DoclingDocument
  -> ExtractedDocument
  -> Alignment
  -> enriched EngineeringDocument
```

Markdown is an export format and is not used as the canonical or intermediate representation.

Native files are stored at:

```text
.atlas/docling/<document-key>/document.json
.atlas/docling/<document-key>/conversion.json
```

---

## File System Adapter

Provides persistence for the canonical EngineeringDocument.

### Import

- load EngineeringDocument

### Export

- persist EngineeringDocument

Documents are stored inside

```
.atlas/documents/
```

---

## Planned Adapters

### Import

- semantic Docling-to-AtlasData alignment
- Markdown
- IntelliDoc
- Polarion
- BASIL
- Travelogue

### Export

- Markdown
- HTML
- PDF
- Graph
- Traceability API

### Round-trip

- Markdown
- AtlasData
- Travelogue

---

# Security Model

Standards Atlas explicitly separates original engineering content from publicly distributable knowledge.

```
PDF
        │
        ▼
DoclingDocument / ExtractedDocument
        │
        ▼
Clause.content
        │
        ▼
Transformation Pipeline
        │
        ▼
ClauseAnnotation
        │
        ├────────────► AtlasData
        │                 │
        │                 ├── TOC
        │                 └── PublicTXT
        │
        └────────────► Doorstop
                          │
                          ├── complete text
                          ├── public annotations
                          ├── local annotations
                          └── private annotations
```

This architecture prevents accidental publication of copyrighted engineering text.

---

# Typical Workflow

```
Engineering Standard PDF + AtlasData

        │

        ├──► DoclingDocument / ExtractedDocument
        │
        └──► EngineeringDocument structure

                    │

                    ▼

        enriched EngineeringDocument

        │

        ▼

Transformation Pipeline

        │

        ▼

Doorstop

        │

        ▼

Requirements Engineering
Traceability
Safety Case
Reviews
```

---

# Current Features

## Domain

- immutable Pydantic domain model
- EngineeringDocument
- Standard
- Clause
- structured ContentBlocks
- SourceEvidence
- ClauseAnnotation
- semantic roles
- engineering document abstraction

## Application

- application services
- import/export ports
- repository abstraction
- transformation pipeline

## AtlasData

- metadata parser
- compiler
- domain mapper
- round-trip support
- heading preservation
- public export

## Doorstop

- deterministic identifier generation
- complete engineering document export
- Git workspace generation
- validation
- standards metadata export

## Docling

- optional PDF conversion adapter
- native JSON persistence under `.atlas`
- adapter-neutral extracted document model
- conversion metadata and source hashing
- extraction inspection without Docling runtime

## Infrastructure

- Hexagonal Architecture
- local repository
- uv-based development
- Typer CLI

---

# Command Line Interface

Import an AtlasData document

```bash
uv run standards-atlas document import data/EN50716
```

Generate AtlasData TOC

```bash
uv run standards-atlas atlasdata generate-toc data/EN50716
```

Update AtlasData

```bash
uv run standards-atlas atlasdata generate-toc data/EN50716 --write
```


Convert a PDF with Docling

```bash
uv sync --extra docling
uv run standards-atlas docling convert ~/standards/EN50716.pdf \
    --document EN50716
```

A repeated conversion reuses the native artifact when the PDF hash is unchanged. If the source PDF has changed or the persisted extraction is incomplete, rerun the command with `--overwrite`. Conversion metadata records the source hash, Docling version, UTC timestamp, and effective pipeline options.

Inspect a persisted Docling extraction

```bash
uv run standards-atlas docling inspect EN50716
```

The inspection reports item counts, page-provenance coverage, and unknown Docling labels. Unknown labels are retained as `ExtractedUnknown` instead of being silently discarded. Detailed integration notes are available in `docs/development/docling-integration.md`.

Export to Doorstop

```bash
uv run standards-atlas document export doorstop EN50716
```

Export to another directory

```bash
uv run standards-atlas document export doorstop EN50716 \
    --target /tmp/EN50716
```

---

# Development

Install dependencies

```bash
uv sync
```

Run the regular test suite

```bash
uv run pytest -m "not docling"
```

Run the real Docling PDF integration test

```bash
uv run pytest -m docling
```

Run formatting and linting

```bash
uv run ruff check
uv run ruff format
```

---

# Documentation

## Architecture

- `docs/architecture/principles.md`

## Architecture Decision Records

- ADR 0001 – Python Packaging
- ADR 0002 – Canonical Domain Model
- ADR 0003 – Hexagonal Architecture
- ADR 0004 – Transformation Pipeline
- ADR 0005 – Public and Local Knowledge Separation
- ADR 0006 – Doorstop Export Architecture
- ADR 0007 – Structured Clause Content and Private Source Provenance
- ADR 0008 – Use Docling as the PDF Extraction Adapter
- ADR 0009 – Harden the Docling Extraction Boundary

---

# Roadmap

The architectural foundation is now complete.

The next development phase focuses on semantic transformations and engineering knowledge generation.

## Near Term

- Docling-to-AtlasData alignment
- extracted content normalization
- Markdown renderer
- IntelliDoc migration
- heading synchronization
- structure validation
- summary generation
- relation generation

## Future

- Polarion adapter
- BASIL adapter
- Travelogue adapter
- Graph export
- Traceability API
- Knowledge Graph
- AI-assisted engineering workflows

---

# Contributing

Please read

- `CONTRIBUTING.md`

before contributing.

The project values

- explicit semantics
- clean architecture
- deterministic transformations
- comprehensive automated testing
- small incremental changes

---

# License

See the project license for licensing information.

## Extracted Document Normalization

Before semantic alignment, native Docling observations are transformed into a deterministic,
provenance-preserving `NormalizedExtractedDocument`:

```text
DoclingDocument
    -> ExtractedDocument
    -> NormalizedExtractedDocument
    -> semantic alignment
```

Normalization currently includes:

- Unicode NFC and prose whitespace normalization
- repeated header, footer, and page-number suppression
- conservative repair of line and page hyphenation
- merging of compatible text fragments
- consolidation and reconstruction of lists
- dedicated preservation of preformatted code

The source extraction remains unchanged. Every normalized item records its contributing source
item IDs and PDF provenance. Suppressed page elements remain available as explicit diagnostics.

Run normalization with:

```bash
uv run standards-atlas normalize run EN50716
```

Inspect the persisted result with:

```bash
uv run standards-atlas normalize inspect EN50716
```

Normalized artefacts are stored only below:

```text
.atlas/normalized/<document-key>/document.json
```

Code follows the typed path:

```text
Docling label "code" -> ExtractedCode -> NormalizedCode -> CodeBlock
```

Unlike prose, code preserves indentation, repeated spaces, and line breaks.
