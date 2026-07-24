# Development guide

This section explains how the Standards Atlas codebase maps to the documented architecture and how to extend it without bypassing domain contracts, traceability, or qualification boundaries.

## Development documents

| Topic | Document |
|---|---|
| Packages, layers, and repository layout | [Project layout](project-layout.md) |
| Add importers, exporters, classifiers, and services | [Extending Standards Atlas](extending.md) |
| Unit, integration, regression, and golden-corpus testing | [Testing and qualification](testing-and-qualification.md) |

## Essential companion references

- [Ports and adapters](../architecture/ports-and-adapters.md)
- [Domain model](../architecture/domain-model.md)
- [Processing pipeline](../architecture/processing-pipeline.md)
- [Artifact formats](../reference/artifact-formats.md)
- [ADR index](../architecture/adr/README.md)

## Common development commands

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run standards-atlas --help
```

[Back to documentation home](../README.md)
