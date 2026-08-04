# Roadmap: IntelliDoc refactoring

The original IntelliDoc prototype demonstrated that cross-domain clause relationships can be explored with embedding-based retrieval and structural heuristics. Its implementation was intentionally experimental and is documented as [historical rationale](../history/legacy-relationship-mapping.md).

The refactoring restores that capability on top of the current Standards Atlas domain model and architectural boundaries. The intended service, evidence, lifecycle, and evaluation boundaries are defined in the [relationship-mapping target architecture](../architecture/relationship-mapping.md).

## Goals

- define a canonical relationship model;
- preserve evidence, provenance, model identity, and generation parameters;
- support retrieval-augmented and LLM-assisted relationship discovery;
- use structural context without coupling the domain model to a retrieval framework;
- support cross-domain navigation and review;
- provide repeatable evaluation and human-in-the-loop promotion workflows;
- keep model, vector-store, and runtime integrations behind ports.

## Planned slices

1. Specify relationship entities, evidence, directionality, confidence, and lifecycle.
2. Define ports for candidate retrieval, relationship assessment, persistence, and review.
3. Build an evaluation corpus from known self, sibling, reciprocal, and reviewed cross-domain relations.
4. Implement a baseline embedding retriever without promoting candidates automatically.
5. Add structure-aware reranking and reciprocal evidence.
6. Add LLM-assisted assessment with constrained outputs and complete provenance.
7. Expose reviewed relationships through Markdown, MCP, and future Knowledge Domain capabilities.
8. Qualify candidate configurations and document operational limits.

Historical model and framework choices are inputs to experiments, not predetermined implementation decisions.
