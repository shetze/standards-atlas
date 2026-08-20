<div align="center">

# Standards Atlas

### Structured, traceable document engineering for international standards

**Import · Normalize · Align · Evaluate · Serve · Publish**

[Documentation](docs/README.md) · [Getting started](docs/getting-started/README.md) · [Architecture](docs/architecture/README.md) · [CLI reference](docs/reference/cli-reference.md) · [Architecture decisions](docs/architecture/adr/README.md)

</div>

![Standards Atlas processing pipeline](docs/architecture/diagrams/svg/processing-pipeline.svg)

Standards Atlas turns licensed source documents and open structural baselines into reviewable engineering artefacts. It keeps private source content separate from publishable structure, preserves provenance across every transformation, and makes uncertain decisions explicit rather than hiding them in generated output.

## Why Standards Atlas?

| Capability | What it provides |
|---|---|
| **Catalog-driven onboarding** | Reproducible configuration for single-part and multi-part standards, editions, source files, page selection, and relationships. |
| **Document extraction and normalization** | Docling-based PDF extraction followed by deterministic structural normalization into stable domain contracts, including source-derived visual preservation for formulas that cannot yet be transcribed semantically. |
| **Reference detection and alignment** | Candidate detection, automatic matching against AtlasData baselines, confidence information, and a human review gate. |
| **Traceable engineering documents** | Canonical documents, content blocks, transformation evidence, source lineage, and durable workspace artefacts. |
| **Semantic evaluation** | Reproducible local corpora, versioned prompt/model matrices, protected-content-safe reports, and regression evidence. |
| **MCP access** | Read-only clause tools and resources over stdio or secured Streamable HTTP, with an automated compatibility probe. |
| **Reusable publications** | Markdown and Doorstop outputs generated from canonical models rather than treated as internal source formats. |

## Quick start

```bash
uv sync --dev
uv run standards-atlas --help
```

Inspect and execute a catalog-driven document workflow:

```bash
uv run standards-atlas workflow plan --all
uv run standards-atlas workflow run --all
```

Run the local semantic-evaluation and MCP entry points:

```bash
uv run standards-atlas evaluation --help
uv run standards-atlas mcp --help
```

The workflow intentionally stops at review boundaries when human confirmation is required. See the [getting-started path](docs/getting-started/README.md), the [document workflow](docs/user-guide/document-workflow.md), and the [MCP server guide](docs/user-guide/mcp-server.md) for operational details.

## Documentation

| Area | Start here |
|---|---|
| **First use and guided learning** | [Getting started](docs/getting-started/README.md) · [Tutorials](docs/tutorials/README.md) |
| **Operational tasks** | [User guide](docs/user-guide/README.md) |
| **Architecture and decisions** | [Architecture](docs/architecture/README.md) · [ADR index](docs/architecture/adr/README.md) |
| **Development and qualification** | [Development guide](docs/development/README.md) |
| **Commands, formats, and vocabulary** | [Reference](docs/reference/README.md) |
| **Current and planned direction** | [Project direction](docs/roadmap/README.md) |

## Design principles

- **Traceability before convenience** — every derived artefact should explain where it came from.
- **Review uncertainty explicitly** — automated alignment and semantic analysis may propose; people approve engineering meaning.
- **Keep source content private** — licensed document text remains local unless publication is explicitly permitted.
- **Use canonical domain models** — PDF, AtlasData, Markdown, Doorstop, and MCP are adapters or exchange surfaces.
- **Prefer deterministic transformations** — reproducibility is a prerequisite for qualification and regression testing.
- **Separate application behavior from protocols** — evaluation services remain reusable independently of MCP.

## Project status

Standards Atlas 0.8.2 is an evolving pre-alpha engineering platform. The deterministic document pipeline, local semantic-evaluation workflow, and read-only MCP access are operational. Generated artefacts and model-assisted results are not authoritative standards content and must be reviewed before being used as engineering evidence.

## Development

```bash
uv run pytest
uv run ruff check .
```

Standards Atlas is licensed under the LGPL Version 3.


## Codex access

Codex can consume the read-only Standards Atlas MCP interface without storing
the bearer token in project files:

```bash
uv run standards-atlas mcp codex-config \
  --url http://127.0.0.1:8765/mcp/
```

See `docs/user-guide/codex-integration.md` for setup and verification.


## Current version

This snapshot corresponds to **standards-atlas 0.8.2**. Version 0.8.2 builds on the completed architecture refactoring with auditable qualification-run archives, typed workflow manifests, dimension-aware cascade resolution, visual-formula preservation and transcription enrichment, and optional LLM-assisted normalization-quality qualification.

### Formula transcription enrichment

Visual-only formulas preserved during PDF normalization can be exposed to trusted MCP clients for LaTeX transcription. Submissions are stored as provenance-bearing enrichment artifacts and then deterministically applied to the canonical formula block; MCP writes require the explicit `capabilities.formula_transcription` opt-in.
