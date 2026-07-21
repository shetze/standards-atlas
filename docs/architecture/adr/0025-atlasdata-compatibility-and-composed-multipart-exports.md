# ADR-0025: AtlasData compatibility and composed multi-part exports

- Status: Accepted
- Date: 2026-07-21

## Context

Standards Atlas originally stored engineering standards in the AtlasData
representation.

During the IntelliDoc refactoring the document processing pipeline was rebuilt
around Docling.

The resulting architecture now contains two different views of the same
standard:

```
PDF
    │
    ▼
Docling JSON
    │
    ▼
Normalized EngineeringDocument
    │
    ▼
Exports
```

At the same time AtlasData remains the authoritative editable representation of
the standard structure.

Several compatibility issues had to be solved:

- preserve historical AtlasData syntax
- support multi-part standards
- support supplements such as IEC 61508-3-1
- preserve manually curated headings
- produce stable Doorstop documents
- preserve stable identifiers across exports

## Decision

### AtlasData remains canonical

AtlasData is the canonical editable representation of the engineering
structure.

Docling is considered an extraction format.

EngineeringDocument is the canonical in-memory model.

The resulting flow is

```
PDF
    │
    ▼
Docling
    │
    ▼
AtlasData
    │
    ▼
EngineeringDocument
    │
    ▼
Exports
```

The export pipeline never reconstructs document structure directly from
Docling.

---

### Historical AtlasData syntax remains canonical

AtlasData continues to emit the historical structure syntax

```
[year] [part-reference] ...
```

Example

```
2010 3-s7 3-7.4 3-7.4.1
```

The compatibility reader additionally accepts the legacy parser variant
introduced during previous refactorings.

Writers always emit the historical format.

---

### Part root clauses are persistent model elements

Every physical standard part contains an explicit clause with visible reference
`0`.

Example

```
IEC 61508-1:2010 0
Part 1
```

These clauses are regular EngineeringDocument clauses.

They are

- persisted in AtlasData,
- imported,
- enriched,
- composed,
- exported.

They are ignored during alignment because they have no counterpart inside the
published standard text.

If a historical document does not yet contain such a clause (for example legacy
supplements), the composition service creates a deterministic compatibility
root.

---

### Family composition

Each physical document is processed independently.

After enrichment a composed family document is created.

Composition preserves

- clause order,
- clause identifiers,
- annotations,
- references,
- part root clauses.

No synthetic document hierarchy is reconstructed during export.

---

### AtlasData headings take precedence

Many standards omit explicit heading lines for subordinate clauses.

AtlasData already contains manually reviewed or AI-generated replacement
headings.

Heading priority is therefore

1. detected document heading
2. AtlasData heading
3. optional future AI-generated heading

Replacement headings are stored only as metadata.

They never become part of the protected clause text.

---

### Stable identifiers

The physical document part is part of the canonical clause identity.

Examples

```
IEC 61508-2:2010 7.4
IEC 61508-3-1:2010 7.4
```

remain distinct throughout the pipeline.

Doorstop exports therefore include the physical part in

- atlas-reference
- idx
- keyword
- standard.refID

---

### Doorstop document hierarchy

Doorstop document relationships are derived from the catalog.

Specific engineering relationships take precedence over generic sector
relationships.

Example

```
IEC61508
    └── EN50128
            └── EN50657
                    └── EN50716
```

The hierarchy therefore reflects the engineering dependency graph rather than
only the sector origin.

---

## Consequences

### Advantages

- Stable long-term identifiers.
- Backwards compatibility with historical AtlasData repositories.
- Stable Doorstop publication.
- Support for supplements.
- Separation between extraction and engineering model.
- Manual improvements inside AtlasData survive repeated imports.
- Future AI-generated headings can be introduced without changing the
  document model.

### Disadvantages

- AtlasData remains a maintained intermediate representation.
- Multi-part composition adds an additional workflow stage.
- Part root clauses are engineering artefacts rather than clauses appearing in
  the published standards.

## Alternatives considered

### Reconstruct hierarchy directly from Docling

Rejected.

Docling does not preserve all editorial information required for engineering
exports.

Repeated imports would lose manually curated information.

### Generate synthetic part roots only during Doorstop export

Rejected.

The document hierarchy would differ between exporters and become difficult to
reason about.

Persisting part roots inside the canonical model keeps all exporters
consistent.

### Treat each standard part as an independent family

Rejected.

Many engineering workflows require a composed family document while preserving
the physical publication boundaries.

Supporting both views provides the greatest flexibility.

## References

- ADR-0003 Hexagonal Architecture
- ADR-0004 Transformation Pipeline
- ADR-0006 Doorstop Export
- PR Slice 2: IntelliDoc rebuild
