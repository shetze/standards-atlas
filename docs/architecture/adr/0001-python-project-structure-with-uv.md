# ADR 0001: Adopt a Standard Python Project Structure Using uv

## Status

**Proposed**

## Context

Standards Atlas has evolved over time as a collection of scripts, data directories, and experimental tools. While this structure has enabled rapid experimentation, it increasingly hinders maintainability, extensibility, and reuse.

The current implementation exhibits several architectural issues:

* Domain logic is tightly coupled with command-line scripts, file formats, and tool-specific processing.
* Module imports depend on the current working directory.
* The project lacks a standard Python project structure.
* Dependencies are not managed centrally or reproducibly.
* Tests, command-line tools, future REST APIs, and integrations with tools such as Doorstop or BASIL cannot reliably share a common implementation.
* Adding new functionality increases coupling and technical debt.

At the same time, Standards Atlas is evolving from a collection of scripts into a modular platform for standards analysis, semantic relationships, and traceability.

## Decision

Standards Atlas will gradually be migrated to a standard Python project structure.

The project will adopt:

* **uv** for dependency management, virtual environments, and reproducible builds.
* **pyproject.toml** as the single project configuration file.
* A **src/** layout for all production code.
* A Python package named **standards_atlas** as the shared implementation used by the CLI, adapters, tests, and future APIs.

The initial target structure is:

```text
standards-atlas/
  pyproject.toml
  uv.lock
  README.md

  src/
    standards_atlas/
      __init__.py
      __main__.py
      cli.py

  tests/

  docs/
    architecture/
      adr/
```

Existing scripts located in `tools/` will remain fully functional during the migration. Functionality will be moved incrementally in small, verifiable changes.

## Rationale

`uv` is chosen because it provides fast dependency resolution, reproducible environments, and first-class support for modern Python packaging standards.

The `src/` layout prevents accidental imports from the project root, making import issues visible during development rather than after installation.

The `standards_atlas` package establishes a stable implementation core. The command-line interface, Doorstop adapter, BASIL adapter, IntelliDoc components, automated tests, and future REST APIs should all depend on this shared implementation instead of maintaining separate logic.

This architectural decision introduces no functional changes. It establishes the technical foundation required to gradually decouple the existing codebase.

## Consequences

### Positive

* Dependencies are managed centrally through `pyproject.toml`.
* Development environments become reproducible using `uv`.
* Tests can rely on stable import paths.
* New modules can be organized consistently under `src/standards_atlas/`.
* The migration can proceed incrementally without disrupting existing functionality.
* Future tools can share a common implementation rather than duplicating logic.

### Negative

* Contributors need to install and use `uv` (or understand the `pyproject.toml` based workflow).
* Existing scripts will eventually need to be updated to use the new package structure.
* During the migration, both the legacy and the new architecture will coexist.
* The repository structure will temporarily become larger before it becomes simpler.

## Alternatives Considered

### Poetry

Poetry provides comparable dependency and package management capabilities. It was not selected because `uv` is simpler, significantly faster, and closely follows modern Python standards such as PEP 621.

### requirements.txt

A traditional `requirements.txt` file would require fewer initial changes but does not provide a complete project description, package metadata, CLI entry points, or development dependency management.

### Preserve the Existing Structure

Maintaining the current script-based structure would minimize short-term effort but would make the implementation of the Traceability API, adapters, testing infrastructure, and future extensions increasingly difficult.

## Implementation Plan

The first pull request introduces only the project foundation:

1. Create `pyproject.toml`.
2. Generate `uv.lock`.
3. Create the `src/standards_atlas/` package.
4. Add a minimal command-line interface.
5. Create the `tests/` directory.
6. Create the ADR directory under `docs/architecture/adr/`.
7. Keep all existing scripts fully operational.

Example commands:

```bash
uv sync
uv run standards-atlas --help
uv run python -m standards_atlas
uv run pytest
```

## Decision Date

2026-07-07

