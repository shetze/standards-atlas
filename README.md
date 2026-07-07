# Standards Atlas

Standards Atlas is a semantic traceability platform for engineering standards.

The project aims to provide a technology-independent representation of standards, requirements, concepts, and their relationships. Rather than focusing on a particular requirements management tool, Standards Atlas builds a common semantic model that can be consumed by tools such as Doorstop, BASIL, AI assistants, and future integrations.

The long-term goal is to provide a reusable Traceability API that enables analysis, comparison, and navigation across engineering standards.

---

## Project Status

The project is currently undergoing a major architectural refactoring.

The initial milestones focus on:

* establishing a modern Python project structure,
* introducing a canonical domain model,
* implementing an Atlas Data adapter,
* preparing the Traceability API.

The existing tooling remains available during the migration.

---

## Development Setup

### Requirements

* Python 3.12 or newer
* uv

Install all project dependencies:

```bash
uv sync
```

---

## Running the CLI

Display the available commands:

```bash
uv run standards-atlas --help
```

Inspect an Atlas data file:

```bash
uv run standards-atlas inspect data data/EN50716
```

Display additional information:

```bash
uv run standards-atlas inspect data data/EN50716 --verbose
```

---

## Running the Tests

Run all tests:

```bash
uv run pytest
```

Run a specific test module:

```bash
uv run pytest tests/unit/adapters/atlasdata/test_parser.py
```

---

## Project Structure

```text
src/
    standards_atlas/
        adapters/
        domain/
        application/

tests/

docs/
    architecture/
        adr/

data/
```

### Responsibilities

* **domain** — Technology-independent engineering model.
* **application** — Application services and workflows.
* **adapters** — Import/export adapters for external formats and tools.
* **data** — Legacy Atlas data files and mapping definitions.
* **tests** — Unit and integration tests.

---

## Documentation

Architecture decisions are documented as ADRs:

* `docs/architecture/adr/0001-python-project-structure-with-uv.md`
* `docs/architecture/adr/0002-traceability-centric-architecture.md`

The legacy Atlas data format is documented in:

* `docs/architecture/atlas-data-format.md`

---

## Current Development Roadmap

### PR 1

* Modern Python project structure
* uv-based development environment
* Initial CLI
* Architecture Decision Records

### PR 2

* Atlas Data adapter
* Metadata parser
* Structure expander
* Atlas parser
* Parser tests
* Data inspection CLI

### Next

* Compiler-style Atlas parser
* Canonical domain model
* Traceability API
* Doorstop adapter
* BASIL adapter

