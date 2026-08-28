# ADR 0006: Multipart Families and Publication Views

## Status
Accepted

## Context
Users need family-level Markdown/Doorstop publications, but persisting a synthetic family `EngineeringDocument` duplicates canonical state and creates identity/provenance ambiguity.

## Decision
Physical `EngineeringDocument` instances remain canonical. Family-level composition is represented by a rebuildable `ComposedDocumentView`.

```text
physical EngineeringDocuments -> ComposedDocumentView -> publication adapters
```

The view may be persisted under workspace/cache locations for inspection or reuse, but it is derived and may be rebuilt. It must retain the contributing physical document identities and ordering. Qualification and corpora consume physical documents, not composed family views.

Publication adapters may render Markdown, Doorstop hierarchies, or future formats from the view.

## Consequences
There is no duplicate canonical family document. Publication can evolve independently from document persistence while retaining family-level usability.
