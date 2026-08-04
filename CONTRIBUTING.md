# Contributing to Standards Atlas

Thank you for contributing to Standards Atlas.

Standards Atlas is an engineering knowledge platform that aims to build a technology-independent semantic model for engineering standards and traceability.

The project is currently undergoing a major architectural refactoring. During this phase, consistency and incremental improvements are more important than adding new features quickly.

## Development Philosophy

The project follows a few fundamental principles.

### Build the Domain First

The core of Standards Atlas is its engineering domain model.

Adapters, command-line tools, AI integrations, and export formats should depend on the domain model—not the other way around.

### Traceability is the Core Capability

Standards Atlas is organized around traceability rather than around specific document formats or tools.

Doorstop, BASIL, Markdown, graph databases, AI services, and future integrations are considered adapters.

### Small Pull Requests

Large refactorings should be decomposed into small, reviewable pull requests.

Whenever possible, each pull request should:

* have a single architectural purpose,
* preserve existing functionality,
* include tests,
* leave the project in a working state.

## Development Environment

The project uses **uv** for dependency management.

Install the development environment:

```bash
uv sync --dev
```

Run the command-line interface:

```bash
uv run standards-atlas --help
```

Run all tests:

```bash
uv run pytest
```

## Project structure

The source tree follows the documented architecture rather than treating external formats as the core model. Start with the [project layout](docs/development/project-layout.md), then review [ports and adapters](docs/architecture/ports-and-adapters.md) and the [domain model](docs/architecture/domain-model.md).

The documentation entry points are:

- [documentation home](docs/README.md);
- [development guide](docs/development/README.md);
- [architecture guide](docs/architecture/README.md);
- [reference](docs/reference/README.md).

## Testing

Every new feature should include automated tests whenever practical.

Prefer small unit tests over large integration tests.

A good pull request typically adds tests together with the implementation.

## Architecture Decisions

Significant architectural changes should be documented using Architecture Decision Records (ADRs).

New ADRs should:

* describe the context,
* explain the decision,
* discuss alternatives,
* document consequences.

Architecture documentation is located in:

```text
docs/architecture/
```

## Coding Guidelines

The project aims to follow modern Python practices.

General guidelines:

* Prefer explicit code over clever code.
* Use type hints.
* Keep functions small.
* Avoid global state.
* Separate parsing from business logic.
* Separate domain logic from infrastructure.
* Write descriptive error messages.
* Keep public APIs stable whenever possible.

## Refactoring

Refactoring is encouraged.

However, every refactoring should improve one of the following:

* readability,
* maintainability,
* testability,
* architectural consistency.

Avoid refactorings that only move code without improving its structure.

## Pull Requests

A pull request should ideally:

* address one problem,
* include tests,
* keep the build green,
* include documentation updates if appropriate.

When introducing significant architectural changes, consider adding an ADR.

## Code Reviews

During review we primarily evaluate:

* correctness,
* readability,
* architectural consistency,
* maintainability,
* testability.

Performance optimizations should only be introduced when supported by measurable evidence.

## Long-Term Vision

The long-term goal is to make Standards Atlas a reusable semantic traceability platform for engineering standards.

Every contribution should move the project toward:

* a stable domain model,
* a technology-independent Traceability API,
* modular adapters,
* high-quality automated tests,
* excellent documentation.

