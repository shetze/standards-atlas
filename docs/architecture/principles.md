# Architecture Principles

This document describes the architectural principles that guide the development of Standards Atlas.

Unlike Architecture Decision Records (ADRs), these principles are intended to remain stable over time. They describe *how* we approach problems rather than *which* specific technologies we use.

Every architectural decision should support one or more of these principles.

---

# 1. Model Knowledge, Not Documents

Engineering standards are documents.

Standards Atlas models the engineering knowledge contained within those documents.

Documents are one representation of engineering knowledge—not the knowledge itself.

The domain model should therefore represent concepts such as:

* standards,
* clauses,
* requirements,
* concepts,
* relationships,
* evidence,
* traceability.

rather than pages, files, or export formats.

---

# 2. Traceability is the Core Capability

The primary purpose of Standards Atlas is to capture and expose traceability.

Everything else—including document parsing, AI support, reporting, and export formats—exists to support this capability.

Whenever several implementation options exist, prefer the one that improves traceability.

---

# 3. Domain Before Infrastructure

The domain model is the heart of the system.

Infrastructure exists to support the domain—not the other way around.

The domain model must never depend on:

* Doorstop
* BASIL
* Markdown
* databases
* graph stores
* AI frameworks
* web frameworks

Instead, infrastructure components depend on the domain.

---

# 4. Parse, Don't Execute

Atlas data files are treated as declarative engineering data.

They must never be executed as shell scripts or interpreted as programs.

Parsing should always be explicit, deterministic, and testable.

---

# 5. Semantic Before Syntactic

Standards Atlas is interested in the meaning of engineering information.

The parser should therefore translate document syntax into semantic concepts as early as possible.

For example:

* clauses become Clause objects,
* requirements become Requirement objects,
* mappings become Relationships.

The remainder of the system should operate on these semantic objects rather than on raw text.

---

# 6. One Canonical Domain Model

Every engineering concept should have exactly one canonical representation inside the system.

Doorstop objects, BASIL work items, Markdown files, CSV rows, and graph nodes are external representations.

They should all be translated into the same internal model.

---

# 7. Adapters Are Replaceable

External technologies evolve.

Standards Atlas should therefore isolate external systems behind adapters.

Replacing one adapter should not require changes to the domain model.

Typical adapters include:

* Atlas Data
* Doorstop
* BASIL
* Markdown
* REST
* Graph databases
* AI services

---

# 8. Preserve Human Readability

Engineering knowledge should remain understandable without specialized tools.

Whenever practical:

* use plain text,
* use meaningful identifiers,
* avoid unnecessary complexity,
* prefer explicit structures.

The project values human maintainability over compact machine-oriented encodings.

---

# 9. Incremental Evolution

Large rewrites are risky.

The preferred strategy is incremental improvement through small, verifiable changes.

Each pull request should leave the system in a working state.

---

# 10. Tests Describe Behaviour

Tests should describe observable behaviour rather than implementation details.

Refactoring should be possible without rewriting the majority of the test suite.

Whenever practical:

* unit tests verify individual components,
* integration tests verify collaboration between components.

---

# 11. Stable Public Interfaces

Public interfaces should evolve more slowly than implementations.

Examples include:

* the domain model,
* the Traceability API,
* command-line interfaces,
* adapter interfaces.

Internal implementations may change as long as these interfaces remain stable.

---

# 12. Explicit is Better than Implicit

Standards Atlas values clarity over cleverness.

The project prefers:

* explicit data structures,
* explicit parsing,
* explicit relationships,
* explicit architecture.

Hidden behaviour should be avoided whenever possible.

---

# 13. Architecture is Part of the Product

Architecture documentation is not an afterthought.

ADRs, architecture diagrams, and this document are considered part of the project's implementation.

Good documentation reduces technical debt.

---

# 14. AI Assists—It Does Not Own the Knowledge

AI can support:

* summarization,
* relationship discovery,
* semantic similarity,
* search,
* navigation.

AI should not become the authoritative source of engineering knowledge.

The canonical knowledge remains the explicit domain model managed by Standards Atlas.

---

# 15. Build a Platform, Not an Application

Standards Atlas is intended to become a reusable engineering platform.

The goal is not to build a single end-user application but to provide a semantic foundation that other tools can build upon.

Future consumers may include:

* command-line tools,
* web applications,
* requirements management systems,
* graph databases,
* AI assistants,
* compliance reporting tools,
* engineering workflows.

The platform should therefore expose stable interfaces and remain independent of any particular user interface or technology.

