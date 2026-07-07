i# Contributing to Standards Atlas

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
uv sync
```

Run the command-line interface:

```bash
uv run standards-atlas --help
```

Run all tests:

```bash
uv run pytest
```

## Project Structure

```text
src/
    standards_atlas/
        domain/
        application/
        adapters/

tests/

docs/
    architecture/
        adr/
```

### Domain

The `domain` package contains technology-independent engineering concepts.

Examples include:

* Standard
* Clause
* Requirement
* Concept
* Relationship
* Evidence

The domain model must not depend on Doorstop, BASIL, Markdown, or AI libraries.

### Application

The `application` package contains workflows and orchestration.

It coordinates domain objects but should contain very little business logic.

### Adapters

Adapters translate between the internal domain model and external systems.

Examples include:

* Atlas Data
* Doorstop
* BASIL
* Markdown
* AI services

Adapters should never contain engineering knowledge that belongs in the domain model.

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

