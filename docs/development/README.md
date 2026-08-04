# Development guide

This section explains how the Standards Atlas codebase maps to the documented architecture and how to extend it without bypassing domain contracts, traceability, or qualification boundaries.

## Development documents

| Topic | Document |
|---|---|
| Packages, layers, and repository layout | [Project layout](project-layout.md) |
| Development sequence and architectural guardrails | [Development workflow](development-workflow.md) |
| Add importers, exporters, classifiers, and services | [Extending Standards Atlas](extending.md) |
| Unit, integration, regression, and golden-corpus testing | [Testing and qualification](testing-and-qualification.md) |
| Local model runtime development | [Local LLM](local-llm.md) |
| Docling adapter implementation | [Docling adapter](docling-adapter.md) |
| Documentation ownership and style | [Documentation style guide](documentation-style-guide.md) |
| Release preparation and contract versioning | [Release and versioning](release-and-versioning.md) |

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

## Contributor entry points

- [Contributing guidelines](../../CONTRIBUTING.md)
- [Architecture principles](../architecture/principles.md)
- [Architecture-guided AI development](../methodology/architecture-guided-ai-development.md)
- [CLI reference](../reference/cli-reference.md)
- [Project direction](../roadmap/README.md)

[Back to documentation home](../README.md)
