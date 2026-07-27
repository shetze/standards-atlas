# Evaluation Clause Access

Slice 5.3.1 introduces transport-neutral, read-only access to persisted
`EngineeringDocument` clauses. The application API deliberately has no MCP,
HTTP, CLI, filesystem, or protected-source dependency.

## Application port

`application/services/evaluation/clause_access.py` defines:

- `ClauseProvider`
- `DocumentDescriptor`
- `ClauseDescriptor`
- `ClauseFilter`
- `SamplingStrategy`

The port supports document discovery, clause lookup, filtered listing,
plain-text search, and reproducible sampling. Sampling can be random or
balanced across documents.

## Filesystem adapter

`EngineeringDocumentClauseProvider` implements the port using
`FileSystemEngineeringDocumentRepository`. It only exposes normalized
metadata and the canonical plain-text projection of clause content. Source
paths, PDFs, extraction internals, and arbitrary filesystem access are not
part of the contract.

The filesystem repository now provides a read-only `list()` operation. It
loads persisted payloads by their embedded document keys rather than deriving
keys from sanitized filenames.

## Language filtering

`EngineeringDocument` currently has no canonical language field. A language
filter therefore returns no matches instead of inferring language from clause
text. Explicit language metadata can be added in a later schema slice.

## Follow-up adapters

MCP and possible REST transports should depend only on `ClauseProvider`.
Transport-specific limits, authentication, and serialization belong in those
inbound adapters, not in the clause access service.
