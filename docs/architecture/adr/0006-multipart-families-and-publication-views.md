# ADR 0006: Multipart Families and Runtime Publication Views

## Status
Accepted

## Context
Users need family-level Markdown and Doorstop publications, but a synthetic family `EngineeringDocument` duplicates canonical state and creates identity, provenance, schema-versioning, and cache-invalidation ambiguity. Persisting a derived composition adds no independent lifecycle value because the view can be rebuilt deterministically from the manifest/catalog and the canonical physical parts.

## Decision
Physical `EngineeringDocument` instances remain the only canonical document state. Publication uses a runtime-only `PublicationDocument` read model.

```text
catalog/manifest + physical EngineeringDocuments
                    |
                    v
          runtime PublicationDocument
                    |
              +-----+-----+
              v           v
           Markdown     Doorstop
```

A physical document is projected directly into `PublicationDocument`. A multipart family is composed on demand from its ordered physical part keys. The projection retains the contributing physical document identities and their lineage, but it is never persisted and therefore has no independent schema or compatibility lifecycle.

Composition is deterministic and validates part roots and clause identity. Qualification and corpora consume physical `EngineeringDocument` instances, not publication projections.

## Consequences
There is no duplicate canonical family document and no stale composed-view cache. Export commands receive family part identities from the workflow/catalog and rebuild the publication read model when needed. Publication formatting can evolve independently of canonical document persistence without introducing another persisted contract.
