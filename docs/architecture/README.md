# Architecture

Standards Atlas uses a hexagonal architecture around canonical document models and a staged, evidence-preserving transformation pipeline. The architecture separates extraction technology, structural knowledge, review decisions, and output formats so each can evolve without becoming the system's internal representation.

![Architecture overview](diagrams/svg/architecture-overview.svg)

## Architecture documents

| Topic | Document |
|---|---|
| System boundaries and actors | [System context](system-context.md) |
| End-to-end transformations | [Processing pipeline](processing-pipeline.md) |
| Canonical entities and contracts | [Domain model](domain-model.md) |
| Application core and adapters | [Ports and adapters](ports-and-adapters.md) |
| Workspace artefacts and provenance | [Persistence and lineage](persistence-and-lineage.md) |
| Planning, execution, and review gates | [Workflow orchestration](workflow-orchestration.md) |
| Doorstop family structure | [Doorstop document hierarchy](doorstop-document-hierarchy.md) |
| Publication and licensed-content boundaries | [Security and copyright](security-and-copyright.md) |

## Design records and visual material

- [Architecture Decision Record index](adr/README.md) — all ADRs grouped by architectural concern.
- [Diagram catalog](diagrams/README.md) — all SVG diagrams with links to editable draw.io sources.

## Architectural goals

- keep the domain model independent of PDF, AtlasData, Markdown, and Doorstop;
- separate source extraction from semantic normalization and alignment;
- preserve evidence and lineage across every transformation;
- make uncertain decisions reviewable instead of hiding them;
- enforce public, local, and private content boundaries;
- support single-part and composed multi-part standards;
- keep transformations deterministic unless an explicit extension says otherwise.

## Related documentation

- [Core user concepts](../user-guide/concepts.md)
- [Workspace guide](../user-guide/workspace.md)
- [Artifact format reference](../reference/artifact-formats.md)
- [Developer guide](../development/README.md)
- [Documentation home](../README.md)

- [MCP Clause Server](mcp-clause-server.md)
