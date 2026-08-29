# ADR 0001: Architecture Principles and Traceability

## Status
Accepted

## Goal alignment
Standards Atlas is a **traceable knowledge-engineering platform for structured technical documents**. Its durable purpose is to transform source publications into canonical `EngineeringDocument` representations and from them into qualified, machine-processable knowledge. LLMs, OWL stores, retrieval engines, MCP, Doorstop, and visualization technologies are means or consumers, not the identity of the system.

Traceability is therefore a product property: every material semantic assertion must remain attributable through its derivation and provenance to the clause, canonical document, and source evidence from which it originated.

## Context
Standards Atlas transforms heterogeneous standards sources into traceable, machine-processable engineering knowledge while preserving durable source evidence. The architecture must preserve provenance and traceability while allowing extraction, publication, retrieval, and LLM technology to evolve independently.

## Decision
Standards Atlas uses a traceability-centric hexagonal architecture and an explicit transformation pipeline.

- The **domain model** contains technology-independent engineering concepts and invariants.
- The **application layer** coordinates use cases through ports and services.
- **Adapters** integrate Docling, AtlasData, Doorstop, LLM providers, filesystems, MCP, and retrieval backends.
- Dependencies point inward; reusable domain and application code do not depend on concrete adapters.
- Architecture tests enforce package-wide dependency direction and selected capability boundaries.
- Every material transformation produces or preserves enough provenance to reconstruct its inputs, rule/configuration identity, and output lineage.
- Persisted derived artifacts are reproducible evidence, not alternate sources of truth.

The preferred data flow is:

```text
source evidence -> normalized evidence -> EngineeringDocument -> context (CBox) -> domain knowledge (ABox/TBox) -> retrieval/serving -> applications
```

## Boundaries
Tooling choices such as `uv`, individual LLMs, graph stores, or publication engines are implementation details unless they alter an architectural boundary or evidence contract.

## Consequences
The architecture favors explicit intermediate artifacts and stable contracts over direct source-to-target conversion. New integrations should normally be adapters; new transformations should be independently testable and auditable.

The dependency rule is executable architecture. The architecture test suite scans the complete active `domain` and `application` package trees rather than a selected list of files. It rejects outward dependencies from domain to application/adapters/CLI, concrete adapter or CLI dependencies from application code, and direct use of selected infrastructure frameworks in the reusable core. Capability-specific guards additionally protect boundaries such as generic evaluation versus semantic qualification and structural taxonomy versus semantic classification.
