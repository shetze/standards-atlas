## Unreleased

### Added

- Add Slice 5.3.4 local evaluation workflow with reproducible corpus drafts.
- Add manifest-driven prompt and model matrix execution.
- Add content-redacted matrix reports for protected standards corpora.

# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.
The project follows Semantic Versioning.

---

## [0.7.0] - 2026-07

### Added

#### Verification and qualification framework

- Added ADR-0039 and a layered testing strategy for unit, contract, property, integration, workflow, and qualification tests.
- Added reusable filesystem repository contract tests and Hypothesis-based persistence properties.
- Added `standards-atlas qualification golden-corpus` with auditable JSON and Markdown reports.
- Added explicit pytest markers for contract, property, and qualification test classes.

#### New workspace architecture

- Introduced the separation between internal workflow artefacts (`.atlas`) and local user data (`local`).
- Added support for local source document repositories.
- Added dedicated export locations for Markdown and Doorstop publications.

#### Hierarchy-based publication

- Introduced explicit publication hierarchies.
- Added the first hierarchy:

  - Functional Safety

    - IEC 61508
    - ISO 26262
    - EN 50126
    - EN 50128
    - EN 50129
    - EN 50657
    - EN 50716

- Doorstop export is now hierarchy-based instead of document-based.

#### Workflow

- Added deterministic workflow execution.
- Added hierarchy-aware planning.
- Added final Doorstop publish stage.

#### Workflow reports

Every completed workflow run now produces deterministic reports including

- workflow plan
- executed commands
- reused artefacts
- generated artefacts
- SHA-256 hashes
- software versions
- Git revision
- execution timestamps

#### Documentation

Completely reorganised project documentation.

Added

- architecture documentation
- user documentation
- developer documentation
- reference documentation

Introduced draw.io based architecture diagrams.

#### ADRs

Added architectural decisions covering

- multipart standards
- workspace architecture
- publication hierarchies
- deterministic workflow reports
- packaged Doorstop templates

#### Doorstop

- hierarchy-aware publication
- packaged publication templates
- template selection per hierarchy

---

### Changed

#### Internal architecture

Completed the migration to the new processing pipeline.

```
PDF
 ↓
Docling
 ↓
ExtractedDocument
 ↓
NormalizedDocument
 ↓
Reference Detection
 ↓
Alignment
 ↓
EngineeringDocument
 ↓
Content Blocks
 ↓
Exports
```

#### Markdown export

Markdown export is now generated from EngineeringDocuments instead of intermediate representations.

#### Doorstop export

Doorstop export now operates on publication hierarchies instead of individual standards.

---

### Fixed

- improved multipart handling
- improved annex handling
- deterministic document composition
- workflow reproducibility
- corrected document hierarchy generation
- repaired incomplete Docling persistence automatically
- improved golden corpus stability

---

## [0.6.x]

Development snapshots leading to the new architecture.

No stable release.
