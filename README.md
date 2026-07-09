# Standards Atlas

Standards Atlas is an open platform for modelling, analysing, transforming, and navigating engineering knowledge.

Its primary goal is to provide a **technology-independent semantic representation** of engineering documents, enabling traceability across standards, requirements, safety cases, architecture specifications, and engineering repositories.

The project is built around a canonical **EngineeringDocument** model that acts as an intermediate representation (IR) between different engineering tools and document formats.

---

## Vision

Engineering knowledge exists in many different forms:

- international standards
- requirements specifications
- safety cases
- architecture descriptions
- compliance evidence
- engineering reports

Although these artifacts often describe the same concepts, they are usually disconnected.

Standards Atlas establishes a common semantic representation that allows these sources to be connected through explicit traceability relationships and semantic analysis.

The long-term vision is an **Engineering Knowledge Platform** with a reusable **Traceability API**.

---

## Architecture

Standards Atlas follows a Hexagonal (Clean) Architecture.

```
                 CLI
                  │
                  ▼
         Application Services
                  │
          Application Ports
                  │
                  ▼
        EngineeringDocument
                  ▲
                  │
      ┌───────────┴────────────┐
      │                        │
 AtlasData Adapter      Future Adapters
                        (Doorstop, BASIL,
                         Markdown, ...)
```

The **EngineeringDocument** model is the canonical representation of engineering knowledge.

Adapters translate external formats into this model.

Application services implement reusable workflows and document transformations.

---

# Current Capabilities

The project already provides a complete round-trip workflow for AtlasData files.

Current workflow:

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
Application Services
      │
      ▼
AtlasData Round-Trip Writer
      │
      ▼
Updated AtlasData File
```

Currently implemented:

- import AtlasData files
- expand clause structure
- build canonical EngineeringDocument objects
- infer semantic roles
- generate TOC initialization records
- preserve manually maintained heading information
- safely update AtlasData files
- automatically create numbered backups before modifications

---

# Development Status

## Foundation

Completed

- Modern Python packaging
- uv-based development environment
- Typer CLI
- Test infrastructure
- Architecture Decision Records

## Canonical Domain Model

Completed

- EngineeringDocument
- Standard
- Clause
- Relation
- SemanticRole
- Pydantic-based immutable domain model

## AtlasData Adapter

Completed

- Metadata parser
- Structure compiler
- Compiler-style parsing pipeline
- Domain mapper
- Round-trip capable AtlasData writer

## Application Layer

Completed

- Adapter ports
- Import services
- AtlasData TOC generation service
- Round-trip update workflow

---

# Current Project Structure

```
src/
    standards_atlas/

        domain/
            EngineeringDocument
            Clause
            Relation
            SemanticRole

        application/
            ports/
            services/

        adapters/
            atlasdata/

        cli/

tests/

docs/
```

---

# Development Setup

Requirements:

- Python 3.12+
- uv

Install dependencies:

```bash
uv sync
```

---

# Running the CLI

Show all commands:

```bash
uv run standards-atlas --help
```

Inspect an AtlasData document:

```bash
uv run standards-atlas inspect data data/EN50716
```

Generate TOC records (dry run):

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083
```

Update the file:

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083 --write
```

A numbered backup of the original file is automatically created before any modifications are written.

---

# Running the Tests

Run the complete test suite:

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

The current architecture is intentionally designed around a canonical intermediate representation (`EngineeringDocument`).

Upcoming work focuses on extending the platform rather than replacing existing functionality.

Planned next steps include:

- document transformation pipeline
- semantic classification
- traceability graph generation
- Doorstop adapter
- BASIL adapter
- Markdown adapter
- cross-standard relationship analysis
- Traceability API

---

# Contributing

Please read

- CONTRIBUTING.md

before contributing.

Architecture consistency is considered more important than rapid feature growth.

---

# License

See the project's license file.
