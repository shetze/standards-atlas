# ADR-0032: End-to-End Artifact Lineage

## Status

Accepted

## Context

The deterministic Transformation Ledger introduced in ADR-0031 explains changes inside
normalization, but it does not identify the artifacts produced before and after that stage.
A generated Markdown or Doorstop artifact must be traceable back through the canonical
EngineeringDocument and NormalizedDocument to the Docling extraction and source document.
File names and timestamps are insufficient because they are mutable and environment-specific.

## Decision

Standards Atlas uses content-addressed artifact references and direct parent relationships.
Each reference contains a stable artifact ID, kind, SHA-256 content hash, and optional location
and media type. IDs have the form `artifact:<kind>:<hash-prefix>`.

The lineage chain is embedded in canonical document contracts:

1. `ExtractedDocument` identifies the Docling extraction and its source document.
2. `NormalizedExtractedDocument` derives from the extraction and records the associated
   Transformation Ledger event IDs.
3. `EngineeringDocument` derives from the normalized artifact and, when available, the prior
   engineering artifact.
4. Markdown and Doorstop adapters emit lineage manifests describing the exported artifact and
   its direct EngineeringDocument parent.

Artifact hashes exclude their own `lineage` field. This prevents recursive identities and makes
lineage metadata additive rather than identity-defining. Export hashes cover the generated file
or the sorted set of files in the export directory. Runtime timestamps are not part of lineage.

## Consequences

- Any exported artifact can be traced to its direct canonical parent.
- Canonical artifacts retain stable identities across identical runs and locations.
- Transformation events are connected to the normalized artifact without duplicating the ledger.
- Markdown produces `<file>.lineage.json`; Doorstop produces `lineage.json` in its root.
- Engineering document persistence advances to schema version 3 while version 2 remains readable.
- The NormalizedDocument schema advances to version 9.

## Limits

This slice records direct ancestry, not a centralized graph database. Alignment and review
artifacts are not yet first-class lineage nodes; the enriched EngineeringDocument currently
records the normalized and preceding engineering artifacts as its direct inputs. A later slice
may add signed manifests, external provenance stores, and explicit alignment/review nodes.
