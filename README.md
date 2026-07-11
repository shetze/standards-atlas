# Standards Atlas

Standards Atlas is an open platform for importing, transforming, analysing, and publishing engineering knowledge.

The project provides a canonical semantic representation of engineering documents that enables traceability across standards, safety cases, requirements, engineering repositories, and future AI-assisted workflows.

Rather than being tied to a specific document format or engineering tool, Standards Atlas is designed as a transformation platform built around a common intermediate representation.

---

# Vision

Engineering knowledge exists in many different forms:

- international standards
- requirements specifications
- safety cases
- architecture descriptions
- engineering reports
- compliance evidence

Although these artefacts often describe the same engineering concepts, they are usually isolated from one another.

Standards Atlas establishes a canonical representation that allows these sources to be connected through semantic transformations, traceability relationships, and knowledge generation.

The long-term vision is an **Engineering Knowledge Platform** providing a reusable **Traceability API**.

---

# Core Concepts

## EngineeringDocument

The canonical domain model.

Every external representation is imported into an immutable
`EngineeringDocument`.

This model serves as the project's **Intermediate Representation (IR)**.

---

## Clause

Represents the original document structure.

A clause contains information originating from the source document:

- identifier
- reference
- clause type
- semantic roles
- original heading
- original text (if available)

The clause itself represents the original engineering artefact.

---

## ClauseAnnotation

Represents additional knowledge associated with a clause.

Unlike the original clause, annotations are generated or maintained by
users or transformation pipelines.

Examples include:

- generated titles
- summaries
- comments
- explanations
- rationale
- examples
- notes
- discussions

Multiple annotations may exist for the same clause.

---

## Annotation Visibility

Every annotation has an explicit visibility.

```
PUBLIC
LOCAL
PRIVATE
```

Only `PUBLIC` annotations may be exported into the public AtlasData
repository.

This prevents accidental publication of copyrighted engineering content.

---

# Architecture

Standards Atlas follows a Hexagonal / Clean Architecture.

```
                CLI
                 │
                 ▼
        Application Services
                 │
                 ▼
      Transformation Pipeline
                 │
                 ▼
        EngineeringDocument
      (Intermediate Representation)
                 ▲
                 │
        Import / Export Ports
                 ▲
                 │
      Source / Target Adapters
```

The domain model is completely independent of external file formats.

---

# Transformation Pipeline

The transformation pipeline contains all semantic processing.

Typical transformations include:

- structure validation
- heading synchronisation
- placeholder resolution
- semantic role inference
- annotation generation
- relation generation
- traceability validation

Transformations always operate on the canonical
`EngineeringDocument`.

---

# Persistence

The canonical intermediate representation can be stored locally.

```
.atlas/

    documents/

        EN50716.json

    transformations/

    warnings/
```

This workspace contains derived engineering knowledge.

Source documents remain the authoritative source.

---

# AtlasData

AtlasData currently serves as the primary public source format.

Current capabilities:

- import AtlasData
- compiler-style structure expansion
- metadata parsing
- domain mapping
- semantic role inference
- round-trip TOC generation
- preservation of manually maintained headings
- numbered backup generation

AtlasData currently exports only information explicitly intended for
publication.

```
TOC
PublicTXT
```

Internal clause text is never exported.

---

# Security Model

The project distinguishes between internal engineering knowledge and
publicly distributable information.

```
PDF / Markdown
        │
        ▼
Clause.text
        │
        ▼
Transformation Pipeline
        │
        ▼
ClauseAnnotation
        │
        ▼
AtlasData Export

    TOC
    PublicTXT
```

This architecture ensures that copyrighted standard text cannot
accidentally be committed into the public AtlasData repository.

---

# Current Project Structure

```
src/
    standards_atlas/

        domain/

            model/

                EngineeringDocument
                Clause
                ClauseAnnotation
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

# Development Status

## Completed

- modern Python packaging
- uv-based development environment
- Typer CLI
- immutable Pydantic domain model
- Hexagonal Architecture
- AtlasData adapter
- compiler-style structure expansion
- canonical EngineeringDocument model
- semantic roles
- ClauseAnnotation model
- public/private annotation model
- application services
- transformation layer
- file-based repository
- AtlasData round-trip workflow

---

# Command Line Interface

Import an AtlasData document

```bash
uv run standards-atlas document import data/EN50716
```

Inspect a document

```bash
uv run standards-atlas inspect data data/EN50716
```

Generate public TOC information

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083
```

Update an AtlasData file

```bash
uv run standards-atlas atlasdata generate-toc data/ISO5083 --write
```

The round-trip writer automatically creates numbered backups before
modifying the original file.

---

# Development

Install dependencies

```bash
uv sync
```

Run all tests

```bash
uv run pytest
```

---

# Documentation

Architecture Principles

- docs/architecture/principles.md

Architecture Decision Records

- docs/architecture/adr/

Current ADRs

- ADR 0001 — Python Packaging
- ADR 0002 — Canonical Domain Model
- ADR 0003 — Hexagonal Architecture
- ADR 0004 — Transformation Pipeline
- ADR 0005 — Separation of Public and Local Knowledge

---

# Roadmap

The architectural foundation is now complete.

Future work focuses on expanding the transformation pipeline and adding
new engineering ecosystems.

Planned work includes:

- IntelliDoc migration
- Markdown importer
- Heading Synchronisation transformation
- Structure Validation transformation
- Annotation generation
- Relation generation
- Doorstop adapter
- BASIL adapter
- Travelogue adapter
- Graph export
- Traceability API

---

# Contributing

Please read

- CONTRIBUTING.md

before contributing.

The project values architectural consistency, explicit semantics,
small incremental changes, and comprehensive automated testing.

---

# License

See the project license for licensing information.
