# ADR 0004 – Adopt a Transformation Pipeline

## Status

Accepted

## Context

Standards Atlas imports engineering knowledge from heterogeneous sources such as AtlasData files, Markdown-converted standards, Polarion exports, Doorstop repositories, BASIL, and future APIs.

These sources are not equally complete or equally reliable. For example, AtlasData may contain a manually defined clause structure, while Markdown-converted PDFs may contain more accurate heading text. Polarion exports may contain requirements, safety levels, status information, and traceability matrices.

The project therefore needs more than import and export adapters. It needs an internal processing model that can validate, enrich, normalize, and connect engineering knowledge after import.

## Decision

Standards Atlas adopts a **Transformation Pipeline** architecture.

Imported artifacts are converted into the canonical `EngineeringDocument` domain model. This model acts as the project’s internal intermediate representation.

Transformations operate on `EngineeringDocument` objects and produce improved `EngineeringDocument` objects or validation reports.

```text
External Sources
      │
      ▼
Import Adapters
      │
      ▼
EngineeringDocument
      │
      ▼
Transformation Pipeline
      │
      ▼
EngineeringDocument
      │
      ▼
Export Adapters
```


## Responsibilities

### Import Adapters

Import adapters translate external sources into the canonical domain model.

Examples:

* AtlasData → EngineeringDocument
* Markdown → EngineeringDocument
* Polarion Export → EngineeringDocument
* Doorstop → EngineeringDocument

Adapters should not own semantic enrichment logic.

### Transformations

Transformations improve, validate, or derive information from documents.

Examples:

* structure validation
* heading synchronization
* placeholder resolution
* semantic role inference
* cross-reference resolution
* relation generation
* traceability validation

### Application Services

Application services orchestrate use cases.

They combine adapters, transformations, repositories, and exporters into user-facing workflows.

### Repositories

The transformed internal view may be persisted as derived intermediate state.

This persistence is not the primary source of truth. Source files and external systems remain authoritative.

## Persistence

The internal transformed representation may be stored in a repository, for example:

```text
.atlas/
  documents/
  transformations/
  warnings/
```

This repository stores derived working state and enables caching, debugging, review, and repeatable workflows.

A repository is accessed through a port, not directly by transformations or adapters.

## Consequences

### Positive

* IntelliDoc functionality has a clear architectural home.
* Import, transformation, persistence, and export are separated.
* The canonical domain model becomes a reusable intermediate representation.
* Multiple sources can contribute to one improved document view.
* Round-trip workflows become explicit and testable.
* Future AI-assisted processing can be implemented as transformations rather than hidden adapter behaviour.

### Negative

* The architecture becomes more layered.
* Some workflows require explicit orchestration.
* Persisted intermediate state must be treated carefully to avoid confusing it with authoritative source data.
* Transformations need clear contracts to avoid hidden side effects.

## Alternatives Considered

### Adapter-Centric Processing

Adapters could directly perform enrichment and validation.

This was rejected because it would couple semantic logic to individual source formats and make reuse difficult.

### Database-Centric Architecture

A database could become the central representation.

This was rejected for now because the canonical domain model should remain independent of storage technology.

### Direct Source-to-Target Conversion

Each source could be converted directly into each target format.

This was rejected because it would create many point-to-point conversions and duplicate semantic logic.

## Decision Outcome

Standards Atlas treats `EngineeringDocument` as its internal intermediate representation.

Adapters import and export.

Transformations enrich and validate.

Application services orchestrate.

Repositories persist derived working state when needed.
