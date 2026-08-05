# User guide

This guide describes the supported user workflows for turning private standards documents into reviewed, traceable engineering artefacts.

## First steps

1. [Install and prepare the project](../getting-started/README.md).
2. [Understand the workspace and core concepts](concepts.md).
3. [Validate a catalog and plan a workflow](catalogs-and-profiles.md).
4. [Run the end-to-end workflow](document-workflow.md).
5. Complete any [alignment](alignment-review.md) or [AtlasData](atlasdata-lifecycle.md) review gate.
6. [Export Markdown or Doorstop output](exports.md).

## Processing and review

| Goal | Guide |
|---|---|
| Configure standards, parts, profiles and hierarchies | [Catalogs and profiles](catalogs-and-profiles.md) |
| Run extraction, normalization, reference detection and construction | [Document workflow](document-workflow.md) |
| Review uncertain clause mappings | [Alignment review](alignment-review.md) |
| Govern public structural baselines | [AtlasData lifecycle](atlasdata-lifecycle.md) |
| Process families made of several publications | [Multi-part standards](multipart-standards.md) |
| Understand generated and local artefacts | [Workspace](workspace.md) |

## Runtime and evaluation

| Goal | Guide |
|---|---|
| Manage the project-owned RamaLama server | [Local LLM operation](local-llm.md) |
| Run the read-only MCP server | [MCP server](mcp-server.md) |
| Connect Codex to MCP | [Codex integration](codex-integration.md) |
| Build corpora and execute qualification matrices | [Evaluation and qualification](evaluation-and-qualification.md) |
| Review generated annotation proposals | [Annotation review](semantic-annotation-review.md) |
| Diagnose common failures | [Troubleshooting](troubleshooting.md) |

The [CLI reference](../reference/cli-reference.md) lists command groups and options. Architecture rationale belongs in [Architecture](../architecture/README.md), not in this task-oriented guide.


## Scope of this guide

The user guide is task-oriented. End-to-end learning paths belong in [Tutorials](../tutorials/README.md), exact option and format definitions belong in [Reference](../reference/README.md), and design rationale belongs in [Architecture](../architecture/README.md).

## Structured knowledge

- [Evaluation and qualification](evaluation-and-qualification.md) explains clause eligibility and the planned table-specific corpus.
- [Table semantics](../architecture/table-semantics.md) describes addressable table records and portable relations.
