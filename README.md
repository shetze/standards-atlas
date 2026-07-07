# Standards Atlas

Standards Atlas is an open platform for modelling, analysing, and navigating engineering knowledge.

Its primary goal is to provide a **technology-independent semantic representation** of engineering standards, requirements, concepts, and traceability relationships.

Rather than being tied to a particular requirements management tool, Standards Atlas establishes a canonical domain model that can be consumed by adapters for tools such as Doorstop, BASIL, AI assistants, graph databases, and future engineering applications.

---

## Vision

Engineering knowledge exists in many different forms:

* international standards
* requirements specifications
* compliance evidence
* safety cases
* architecture descriptions
* engineering documentation

Although these artifacts often describe the same concepts, they are usually disconnected.

Standards Atlas aims to establish a common semantic representation that allows these sources to be connected through explicit traceability relationships.

The long-term vision is to provide an **Engineering Knowledge Platform** built around a reusable **Traceability API**.

---

## Architecture

Standards Atlas follows a Hexagonal Architecture.

```text
                CLI
                 │
                 ▼
       Application Services
                 │
                 ▼
           Domain Model
                 ▲
                 │
      ┌──────────┴──────────┐
      │                     │
 Atlas Data Adapter   Future Adapters
```

The domain model contains the engineering concepts.

Adapters translate external representations into the canonical model.

Application services implement the behaviour of the platform.

---

## Current Status

The project is currently undergoing a staged architectural migration.

### PR1 – Project Foundation

Completed

* Modern Python project structure
* uv-based development environment
* Initial CLI
* Architecture Decision Records

### PR2 – Atlas Data Adapter

Completed

* Atlas data format specification
* Metadata parser
* Structure parser
* Structure compiler
* Atlas parser
* Integration tests
* Data inspection CLI

### PR3 – Canonical Domain Model

Completed

* Pydantic-based domain model
* Standard, Clause and Relation entities
* Atlas Data → Domain mapper
* Compiler-style parser architecture
* CLI migrated to the domain model
* Hexagonal architecture

### Next Steps

Planned work includes:

* Application Services
* Traceability API
* Knowledge Domains
* Doorstop Adapter
* BASIL Adapter
* Semantic Analysis Services

---

## Development Setup

### Requirements

* Python 3.12 or newer
* uv

Install all dependencies:

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

Display detailed information:

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
        domain/
        application/
        adapters/
        cli/

tests/

docs/
    architecture/
        adr/

data/
```

### Responsibilities

* **domain** – Technology-independent engineering concepts.
* **application** – Use cases and orchestration.
* **adapters** – Import/export adapters for external technologies.
* **cli** – Command-line interface.
* **data** – Legacy Atlas data files.
* **tests** – Unit and integration tests.

---

## Documentation

Architecture principles:

* `docs/architecture/principles.md`

Architecture Decision Records:

* `docs/architecture/adr/`

Technical specifications:

* `docs/architecture/atlas-data-format.md`

---

## Contributing

Please read:

* `CONTRIBUTING.md`

before contributing to the project.

Architecture consistency is considered more important than rapid feature growth.

---

## License

See the project's license file for licensing information.

