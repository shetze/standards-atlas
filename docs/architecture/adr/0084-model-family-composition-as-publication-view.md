# ADR 0084: Model family composition as a rebuildable publication view

## Status

Accepted

## Context

Multi-part standards are represented canonically by their physical part documents. Historically,
`document compose-family` copied all part clauses into a second `EngineeringDocument` persisted as
`.atlas/data/documents/<family>.json`. Markdown and Doorstop publication consumed that copy.

The persisted family copy duplicated clause identity and content, forced evaluation code to filter
family duplicates, and became increasingly problematic as tables, formal semantics, and retrieval
projections acquired their own identity and provenance.

The AtlasData family master is still useful while deriving physical part documents, but it is not a
canonical engineering document after derivation.

## Decision

Canonical document storage contains physical documents only.

For multi-part families:

1. the AtlasData family master is imported temporarily below `.atlas/work/family-sources`;
2. physical part documents are derived into `.atlas/data/documents`;
3. `document compose-family` builds a `ComposedDocumentView` from those canonical parts;
4. the view is persisted as a rebuildable publication projection below
   `.atlas/work/composed-documents/<family>.json`;
5. Markdown and Doorstop publication resolve family keys through that view;
6. an obsolete canonical `.atlas/data/documents/<family>.json` is removed when a new view is
   composed.

`ComposedDocumentView` is not a canonical knowledge artifact. It may be deleted with `.atlas/work`
and regenerated from the physical parts.

Qualification and corpus providers enumerate only the canonical engineering-document repository.
The existing exact-occurrence deduplication remains temporarily as a legacy safeguard for workspaces
created before this decision.

## Consequences

- Clause, table, semantic, and retrieval identities have one canonical physical-document owner.
- Publication can still expose a logical standard family in catalog order.
- Clearing `.atlas/work` removes publication views but never canonical part documents.
- Markdown and Doorstop adapters must resolve both canonical single documents and composed family
  views.
- Workflow recovery treats composed views as derived work artifacts.

## Supersedes

This decision supersedes the provisions in ADR 0025 that persist a composed family as an
`EngineeringDocument` in the canonical document repository.
