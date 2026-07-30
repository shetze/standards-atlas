# Evaluation clause access

Semantic qualification needs read-only access to clauses without coupling its
application logic to MCP, HTTP, CLI commands, persistence file layouts, or
protected source documents. This boundary is expressed by the transport-neutral
`ClauseProvider` application port.

## Canonical application port

The canonical definitions live in:

```text
src/standards_atlas/application/semantic_qualification/clause_access.py
```

The module defines:

- `ClauseProvider`
- `DocumentDescriptor`
- `ClauseDescriptor`
- `ClauseFilter`
- `SamplingStrategy`

The port supports document discovery, stable clause lookup, filtered listing,
plain-text search, and reproducible sampling. Available strategies include
random, balanced-by-document, and representative-stratified sampling.

For migration compatibility, `ClauseProvider` is also re-exported from
`application.services.evaluation`. New code should use the canonical
`application.semantic_qualification.clause_access` path.

## Descriptor boundary

`DocumentDescriptor` and `ClauseDescriptor` expose only data required by
qualification clients. A clause descriptor contains stable identity,
document key, reference, content hash, clause type, title, canonical plain-text
content, hierarchy information, and statement functions.

The contract deliberately excludes:

- source PDF paths;
- Docling and normalization internals;
- arbitrary filesystem access;
- persistence payload details;
- mutable domain aggregates.

This keeps remote transports and evaluation workflows independent of protected
source locations and storage implementation details.

## Filesystem adapter

```text
src/standards_atlas/adapters/evaluation/
    EngineeringDocumentClauseProvider
```

`EngineeringDocumentClauseProvider` implements the application port using
`FileSystemEngineeringDocumentRepository`. It reads persisted canonical
`EngineeringDocument` objects and projects them into immutable descriptors.
Document identities are taken from embedded document keys rather than inferred
from sanitized filenames.

## Filtering and language

Filters cover document keys, document types, clause types, statement functions,
and text-length limits. `EngineeringDocument` currently has no canonical
language field. A requested language filter therefore yields no matches rather
than guessing from clause text.

## Inbound adapters

MCP and any future REST or GraphQL endpoint must depend on `ClauseProvider`, not
on the filesystem repository. Authentication, exposure limits, request
validation, serialization, and transport errors belong to those inbound
adapters.
