# Standards Atlas

Standards Atlas is an open-source toolkit for building a semantically structured representation of engineering standards.

The project separates **document extraction**, **semantic alignment**, **canonical engineering data**, **analysis**, and **export** into independent architectural layers. This enables the same engineering knowledge to be reused for different purposes such as requirements management, documentation, traceability, semantic search, AI-assisted analysis, and future tooling.

The canonical representation of a standard is **not Markdown**. Instead, Standards Atlas maintains a structured internal model that serves as the single source of truth throughout the entire processing pipeline.

---

## Motivation

Engineering standards are typically distributed as PDF documents that are optimized for human readers but difficult to process automatically.

A PDF primarily describes the visual appearance of a document rather than its semantic structure. Although modern extraction tools such as Docling can reconstruct much of this structure, the result is still an approximation.

Standards Atlas combines two complementary information sources:

- **AtlasData** provides the expected semantic document structure.
- **Docling** extracts the actual content from the original PDF.

Both sources are combined into a canonical engineering model that preserves the semantic structure while maintaining traceability back to the original document.

---

# Architecture

The overall processing pipeline is shown below.

```text
                    +----------------+
                    |  AtlasData     |
                    +----------------+
                             |
                             |
                             v
                   EngineeringDocument
                 (canonical document model)
                             ^
                             |
                 Document Alignment Engine
                             ^
                             |
                   Raw DoclingDocument
                             ^
                             |
                         Docling
                             ^
                             |
                            PDF
```

Once the canonical document has been created, it becomes the basis for all further processing.

```text
EngineeringDocument
        │
        ├── Markdown Export
        ├── Doorstop Export
        ├── AI-assisted IntelliDoc workflows
        ├── Embeddings
        ├── Semantic Search
        └── Future analysis tools
```

**Markdown is therefore an export format, not the internal representation of a standard.**

---

# Design Principles

Standards Atlas follows a number of architectural principles.

## Canonical Engineering Model

The canonical representation of a standard is the `EngineeringDocument`.

Every adapter imports or exports this model.

No adapter communicates directly with another adapter.

---

## Separation of Responsibilities

Each architectural layer has a clearly defined responsibility.

| Layer | Responsibility |
|--------|----------------|
| Domain | Canonical engineering model |
| Application | Processing workflows and business logic |
| Adapters | Import and export of external formats |
| Infrastructure | Persistence and external services |

---

## AtlasData Defines the Structure

AtlasData is considered the authoritative source for

- document hierarchy
- clause identifiers
- clause numbering
- parent-child relationships
- document metadata

The semantic structure of a document is therefore independent of any individual PDF.

---

## Docling Performs Extraction

Docling is responsible only for extracting information from PDF documents.

This includes

- paragraphs
- headings
- tables
- figures
- formulas
- page information
- layout information
- reading order

Docling does **not** define the semantic structure of the engineering document.

---

## Alignment Creates Engineering Knowledge

The alignment process combines

- the semantic structure provided by AtlasData, and
- the extracted content provided by Docling.

The result is a complete `EngineeringDocument`.

---

## Adapter Independence

The domain model never depends on Docling, Markdown, Doorstop, or any other external format.

All external technologies are isolated behind adapters.

This makes it possible to replace individual technologies without affecting the rest of the system.

---

# Canonical Data Model

The canonical model consists of three major concepts.

```text
EngineeringDocument
│
├── metadata
├── document structure
└── Clause[]
        │
        ├── reference
        ├── title
        ├── metadata
        ├── content[]
        └── source evidence
```

---

## Structured Clause Content

Each clause contains a sequence of structured content blocks.

Currently supported block types are

| Block | Description |
|--------|-------------|
| TextBlock | Plain text paragraph |
| ListBlock | Ordered or unordered list |
| TableBlock | Table structure |
| PictureBlock | Figures and images |
| FormulaBlock | Mathematical expressions |
| NoteBlock | Notes and remarks |

The ordering of content blocks is preserved exactly as it appears in the source document.

---

## Source Evidence

Every content block may contain provenance information describing where it originated.

Typical information includes

- source document
- page number
- bounding box
- extraction method
- original document reference

The domain model intentionally uses adapter-neutral provenance objects.

No Docling-specific data structures appear in the canonical model.

---

# Repository Structure

```text
src/
├── standards_atlas/
│   ├── domain/
│   ├── application/
│   └── adapters/
│
docs/
│   └── architecture/
│       └── adr/
│
tests/
│
.atlas/
```

---

# Persistent Storage

All generated artefacts containing potentially copyrighted standard content are stored below

```text
.atlas/
```

Typical directory layout:

```text
.atlas/
├── documents/
├── docling/
├── alignments/
└── exports/
```

The `.atlas` directory is intentionally excluded from Git.

This ensures that the public repository contains

- source code
- documentation
- tests
- metadata

but never copyrighted standard documents.

---

# Processing Pipeline

The current architecture processes engineering standards in several stages.

## 1. AtlasData Import

AtlasData imports the semantic document structure.

Result:

```
EngineeringDocument
```

without document content.

---

## 2. PDF Extraction

Docling converts the original PDF into a structured document representation.

Result:

```
DoclingDocument
```

This representation is stored unchanged.

---

## 3. Document Alignment

The alignment engine matches

- Docling elements
- AtlasData clauses

and enriches the canonical engineering model.

---

## 4. EngineeringDocument

The resulting document contains

- semantic structure
- structured content
- provenance information
- engineering metadata

---

## 5. Export

The canonical engineering model can then be exported into different formats.

Currently planned exports include

- Markdown
- Doorstop
- additional engineering formats

---

# Current Status

| Feature | Status |
|----------|:------:|
| AtlasData Import | ✅ |
| Canonical EngineeringDocument | ✅ |
| Structured Clause Model | ✅ |
| Structured Content Blocks | ✅ |
| Schema Versioning | ✅ |
| Doorstop Export | ✅ |
| Docling Integration | 🚧 |
| Document Alignment | 🚧 |
| Markdown Renderer | 🚧 |
| IntelliDoc Workflow | 🚧 |
| Semantic Retrieval | ⏳ |
| Embeddings | ⏳ |
| AI-assisted Analysis | ⏳ |

---

# Roadmap

The planned implementation order is

1. Structured clause model
2. Docling adapter
3. Document alignment engine
4. Markdown renderer
5. IntelliDoc workflow
6. Requirement classification
7. Semantic retrieval
8. Embedding generation
9. AI-assisted document analysis

---

# Documentation

Architectural decisions are documented as Architecture Decision Records (ADRs).

```
docs/
└── architecture/
    └── adr/
```

The ADRs describe the evolution of the architecture and explain the rationale behind major design decisions.

---

# Development Status

Standards Atlas is currently under active development.

The focus of the current development cycle is the integration of PDF-based engineering standards through Docling and the creation of a robust, semantically structured engineering document model.

---

# License

See the project license for details.
