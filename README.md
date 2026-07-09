# Standards Atlas

Standards Atlas is an open platform for importing, transforming, analysing, and exporting engineering knowledge.

The project provides a canonical, technology-independent representation of engineering documents that enables traceability across standards, requirements, architecture specifications, safety cases, and engineering repositories.

Rather than being tied to a specific engineering tool, Standards Atlas acts as a transformation platform built around a common intermediate representation.

---

# Vision

Engineering knowledge exists in many heterogeneous forms:

- international standards
- requirements specifications
- architecture descriptions
- safety cases
- compliance evidence
- engineering reports

Although these artefacts often describe the same concepts, they are typically disconnected and stored in incompatible formats.

Standards Atlas provides a canonical **EngineeringDocument** model that serves as the semantic foundation for traceability, validation, document transformation, and future AI-assisted engineering workflows.

The long-term vision is an **Engineering Knowledge Platform** with a reusable **Traceability API**.

---

# Architecture

Standards Atlas follows a Hexagonal / Clean Architecture.

```
                CLI
                 │
                 ▼
        Application Services
                 │
         Transformation Pipeline
                 │
                 ▼
        EngineeringDocument
      (Intermediate Representation)
                 ▲
                 │
       Import / Export Adapters
                 ▲
                 │
        External Engineering Tools
```

The **EngineeringDocument** model is the project's canonical intermediate representation.

All engineering knowledge is imported into this model, transformed there, and exported again when required.

---

# Current Capabilities

The current implementation already supports a complete AtlasData round-trip workflow.

```
AtlasData File
      │
      ▼
AtlasData Importer
      │
      ▼
EngineeringDocument
      │
      ▼
Transformation Pipeline
      │
      ▼
AtlasData Round-Trip Writer
      │
      ▼
Updated AtlasData File
```

Implemented features include:

- AtlasData import
- compiler-style structure parsing
- canonical EngineeringDocument generation
- semantic role assignment
- TOC generation
- safe AtlasData round-trip updates
- preservation of manually maintained heading records
- automatic numbered backups before writing
- file-based persistence of EngineeringDocument objects

---

# Intermediate Representation

The internal processing model is the immutable `EngineeringDocument`.

Unlike external document formats, this model is independent of storage technology and document syntax.

The model currently supports:

- EngineeringDocument
- Standard
- Clause
- Relation
- SemanticRole

Additional document types can be introduced without affecting the existing architecture.

---

# Transformation Pipeline

Engineering knowledge is processed through independent transformations.

Typical transformations include:

- structure validation
- heading synchronization
- placeholder resolution
- semantic role inference
- relation generation
- cross-reference validation

Transformations operate exclusively on the canonical domain model.

---

# Persistence

Standards Atlas stores derived intermediate state in a lightweight workspace.

```
.atlas/

    documents/
        *.json

    transformations/

    warnings/
```

The repository is **not** the authoritative source of engineering data.

Source documents remain the single source of truth.

The workspace exists to support repeatable transformations, caching, debugging, and future semantic analysis.

---

# Current Project Structure

```
src/
    standards_atlas/

        domain/
            EngineeringDocument
            Clause
            Relation

        application/

            ports/

            repositories/

            services/

            transformations/

        adapters/

            atlasdata/

            filesystem/

        cli/

tests/

docs/
```

---

# Development Setup

Requirements

- Python 3.12+
- uv

Install dependencies

```bash
uv sync
```

---

# Command Line Interface

Display all commands

```bash
uv run standards-atlas --help
```

Inspect an AtlasData document

```bash
uv run standards-atlas inspect data data/EN50716
```

Generate TOC records

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083
```

Update the AtlasData file

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083 --write
```

A numbered backup is automatically created before the original file is modified.

---

# Running the Tests

Run the complete test suite

```bash
uv run pytest
```

---

# Documentation

Architecture Principles

- docs/architecture/principles.md

Architecture Decision Records

- docs/architecture/adr/

Technical Specifications

- docs/architecture/atlas-data-format.md

---

# Roadmap

The architectural foundation is now in place.

Future work focuses on expanding the transformation pipeline and connecting additional engineering ecosystems.

Planned next steps include:

- IntelliDoc migration into the transformation pipeline
- Markdown importer
- Heading synchronization transformation
- Structure validation transformation
- Semantic relation generation
- Cross-standard traceability
- Doorstop adapter
- BASIL adapter
- Graph export
- Traceability API

---

# Contributing

Please read

- CONTRIBUTING.md

before contributing.

The project prioritises architectural consistency, small incremental changes, and comprehensive tests over rapid feature growth.

---

# License

See the project license for licensing information.
