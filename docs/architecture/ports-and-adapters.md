# Ports and adapters

![Ports and adapters](diagrams/svg/ports-and-adapters.svg)

## Architectural target

Standards Atlas follows a hexagonal target architecture. In that target, inbound
adapters such as the CLI and MCP invoke application use cases. Application code
depends on domain types and explicit ports. Outbound adapters implement storage,
LLM access, document conversion, and publication behavior.

```text
Inbound adapters
    CLI, MCP, future APIs
            |
            v
Application use cases and ports
            |
            v
Domain model

Outbound adapters implement application ports:
    filesystem, Docling, AtlasData, LLM, Markdown, Doorstop
```

The intended dependency rule is that the domain has no dependency on application
or adapter packages, and reusable application-core logic does not construct or
import concrete adapters. Concrete implementations are selected at composition
roots, primarily the CLI application tree.

## Current implementation state

The domain boundary already follows the target: canonical models do not import
CLI, persistence, Docling, Doorstop, or other adapter concerns. Newer subsystems,
including generic evaluation and clause access, expose explicit protocols and
are composed with adapters at the edge.

The application layer is still in transition. Several older workflow and
service facades directly import or construct standard filesystem, Docling,
AtlasData, normalization, or export adapters. These classes provide convenient
local composition, but they do not yet satisfy the strict target dependency
rule. They should be understood as application-level composition facades rather
than a fully adapter-independent application core.

Therefore this document is both:

- the authoritative **target** for new architecture and refactoring decisions;
- an explicit record that the current implementation only **partially** reaches
  that target.

New code should not extend the transitional pattern. It should define an
application port, inject the dependency, and place concrete construction in a
composition root. Existing direct imports can be migrated incrementally without
changing domain contracts.

## Current adapter responsibilities

Adapters currently cover:

- Docling PDF conversion and native artifact reading;
- YAML catalog reading;
- AtlasData parsing, lifecycle handling, onboarding, and TOC generation;
- filesystem persistence of engineering documents and intermediate artifacts;
- clause projection for evaluation and MCP access;
- local LLM and external model gateways;
- Markdown export;
- Doorstop export and publication templates;
- MCP transport, authentication, limits, and audit logging.

These boundaries prevent target-specific identifiers, serialization details,
source paths, and tool behavior from leaking into the canonical domain model. A
new importer, exporter, repository, transport, or model provider should
implement a port and translate at the edge rather than add format-specific
fields to the domain.
