# Roadmap

Standards Atlas is being developed as a deterministic engineering platform for analysing, maintaining and publishing relationships between international technical standards, specifications and other engineering documents.

The project is currently replacing the former IntelliDoc implementation with a modern, deterministic architecture while preserving and extending its engineering capabilities.

---

# Long-term Vision

Standards Atlas shall become the reference platform for analysing relationships between standards originating from different standardisation domains.

Initially the focus lies on Functional Safety standards.

Examples include

- IEC 61508
- ISO 26262
- EN 50126
- EN 50128
- EN 50129
- EN 50657
- EN 50716

Later the same approach shall be extended to Cybersecurity, Railway Interoperability and further domains.

---

# Current Refactoring Programme

The current development is not primarily about adding new features.

Its objective is to replace the legacy IntelliDoc implementation by a deterministic and maintainable architecture while preserving all engineering capabilities.

Every completed slice restores one part of the former functionality on top of the new architecture.

---

# Version 0.7

Completed

## Deterministic document pipeline

- Docling integration
- NormalizedDocument
- EngineeringDocument
- deterministic workflows
- reproducible publications

## Workspace redesign

- internal workspace
- local source repository
- hierarchy-based publications

## Functional Safety publication hierarchy

- IEC 61508
- ISO 26262
- EN 50126
- EN 50128
- EN 50129
- EN 50657
- EN 50716

---

# Version 0.8

## Restore IntelliDoc relationship analysis

Reintroduce the engineering functionality that previously existed in IntelliDoc.

### Cross-standard references

Detect

- normative references
- adapted clauses
- inherited requirements
- equivalent concepts
- terminology mappings

### Alignment improvements

Support

- one-to-many mappings
- many-to-one mappings
- partial clause mappings
- confidence assessment
- review workflow

### Knowledge Domain

Represent standards as an explicit graph rather than a publication tree.

Relationship types include

- derives from
- adapts
- supersedes
- references
- constrains
- specialises
- equivalent to

---

# Version 0.9

## Engineering analysis

Generate engineering artefacts directly from the Knowledge Domain.

Examples

- impact analysis
- dependency reports
- missing mappings
- consistency checks
- terminology comparison

## Semantic enrichment

Automatically classify

- requirements
- recommendations
- definitions
- objectives
- assumptions
- rationale

---

# Version 1.0

## Functional Safety Atlas

The first production-ready engineering platform for analysing relationships between Functional Safety standards.

Capabilities include

- deterministic document processing
- reproducible publications
- complete cross-standard navigation
- engineering reports
- qualification evidence
- stable APIs
- stable CLI

---

# Beyond Functional Safety

After completion of the Functional Safety Atlas the same methodology will be applied to further domains.

## Cybersecurity

Examples

- IEC 62443
- ISO/SAE 21434
- IEC 27000 family

## Railway

Examples

- TSI
- CCS
- ERA guidance
- operational rules

## Systems Engineering

Examples

- IEC 81346
- ISO 15288
- SysML-based artefacts

---

# Research Topics

Future research includes

- semantic document comparison
- AI-assisted relationship discovery
- automated impact prediction
- knowledge graph visualisation
- engineering assistants
- configurable publication pipelines

## Completed: Slice 5.3.4 – Local Evaluation Workflow

- Reproducible corpus construction from persisted clauses
- Annotation-ready local datasets and source-hash manifests
- Manifest-driven prompt/model benchmark matrices
- Protected-content-safe matrix reports
