<div align="center">

# Standards Atlas

### Structured, traceable document engineering for international standards

**Import · Normalize · Align · Review · Compose · Export**

[Documentation](docs/README.md) · [Getting started](docs/user-guide/getting-started.md) · [Architecture](docs/architecture/README.md) · [CLI reference](docs/reference/cli-reference.md) · [Architecture decisions](docs/architecture/adr/README.md)

</div>

![Standards Atlas processing pipeline](docs/architecture/diagrams/svg/processing-pipeline.svg)

Standards Atlas turns licensed source documents and open structural baselines into reviewable engineering artefacts. It keeps private source content separate from publishable structure, preserves provenance across every transformation, and makes uncertain decisions explicit rather than hiding them in generated output.

## Why Standards Atlas?

| Capability | What it provides |
|---|---|
| **Catalog-driven onboarding** | Reproducible configuration for single-part and multi-part standards, editions, source files, page selection, and relationships. |
| **Document extraction and normalization** | Docling-based PDF extraction followed by deterministic structural normalization into stable domain contracts. |
| **Reference detection and alignment** | Candidate detection, automatic matching against AtlasData baselines, confidence information, and a human review gate. |
| **Traceable engineering documents** | Canonical documents, content blocks, transformation evidence, source lineage, and durable workspace artefacts. |
| **Standards-family composition** | Composition of parts, annexes, and related standards while preserving their individual identities and hierarchy. |
| **Reusable exports** | Markdown and Doorstop outputs generated from canonical models rather than treated as internal source formats. |

## Quick start

```bash
uv sync --dev
uv run standards-atlas --help
```

Inspect a catalog-driven workflow before executing it:

```bash
uv run standards-atlas workflow plan --all
uv run standards-atlas workflow run --all
```

The workflow intentionally stops at review boundaries when human confirmation is required. See the [getting-started guide](docs/user-guide/getting-started.md) and the [document workflow](docs/user-guide/document-workflow.md) for the complete sequence.

## Documentation

| Area | Start here |
|---|---|
| **Using Standards Atlas** | [User guide](docs/user-guide/README.md) |
| **Understanding the design** | [Architecture](docs/architecture/README.md) |
| **Extending and testing** | [Development guide](docs/development/README.md) |
| **Commands and formats** | [Reference](docs/reference/README.md) |
| **Why the system is designed this way** | [ADR index](docs/architecture/adr/README.md) |
| **Reusable architecture illustrations** | [Diagram catalog](docs/architecture/diagrams/README.md) |

## Design principles

- **Traceability before convenience** — every derived artefact should explain where it came from.
- **Review uncertainty explicitly** — automated alignment may propose; people approve engineering meaning.
- **Keep source content private** — licensed document text remains local unless publication is explicitly permitted.
- **Use canonical domain models** — PDF, AtlasData, Markdown, and Doorstop are adapters or exchange formats.
- **Prefer deterministic transformations** — reproducibility is a prerequisite for qualification and regression testing.

## Project status

Standards Atlas 0.6 is an evolving pre-alpha engineering platform. Generated artefacts are not authoritative standards content and must be reviewed before being used as engineering evidence.

## Development

```bash
uv run pytest
uv run ruff check .
```

Standards Atlas is licensed under the Apache License 2.0.
