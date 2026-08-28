# ADR 0001: Architecture Principles and Traceability

## Status
Accepted

## Context
Standards Atlas transforms heterogeneous standards sources into durable engineering evidence. The architecture must preserve provenance and traceability while allowing extraction, publication, retrieval, and LLM technology to evolve independently.

## Decision
Standards Atlas uses a traceability-centric hexagonal architecture and an explicit transformation pipeline.

- The **domain model** contains technology-independent engineering concepts and invariants.
- The **application layer** coordinates use cases through ports and services.
- **Adapters** integrate Docling, AtlasData, Doorstop, LLM providers, filesystems, MCP, and retrieval backends.
- Dependencies point inward; reusable domain and application code do not depend on concrete adapters.
- Every material transformation produces or preserves enough provenance to reconstruct its inputs, rule/configuration identity, and output lineage.
- Persisted derived artifacts are reproducible evidence, not alternate sources of truth.

The preferred data flow is:

```text
source evidence -> normalized evidence -> canonical model -> deterministic projections -> inferred projections -> publication/retrieval
```

## Boundaries
Tooling choices such as `uv`, individual LLMs, graph stores, or publication engines are implementation details unless they alter an architectural boundary or evidence contract.

## Consequences
The architecture favors explicit intermediate artifacts and stable contracts over direct source-to-target conversion. New integrations should normally be adapters; new transformations should be independently testable and auditable.
