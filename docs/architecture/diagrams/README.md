# Architecture diagram catalog

Every architecture illustration is maintained in two forms:

- `drawio/` contains the editable draw.io source;
- `svg/` contains the generated image embedded by Markdown documents.

Changes should be made in draw.io first and then exported to the SVG with the same base name.

## Core architecture

| Diagram | Purpose | Files |
|---|---|---|
| Architecture overview | Hexagonal system structure and main adapter boundaries | [SVG](svg/architecture-overview.svg) · [draw.io](drawio/architecture-overview.drawio) |
| System context | Users, local source documents, catalogs, and output consumers | [SVG](svg/system-context.svg) · [draw.io](drawio/system-context.drawio) |
| Ports and adapters | Application core, inbound ports, and outbound adapters | [SVG](svg/ports-and-adapters.svg) · [draw.io](drawio/ports-and-adapters.drawio) |
| Domain model | Principal document and content models | [SVG](svg/domain-model.svg) · [draw.io](drawio/domain-model.drawio) |

## Processing and workflow

| Diagram | Purpose | Files |
|---|---|---|
| Processing pipeline | End-to-end transformation from source PDF to exports | [SVG](svg/processing-pipeline.svg) · [draw.io](drawio/processing-pipeline.drawio) |
| User workflow | User-facing stages and review points | [SVG](svg/user-workflow.svg) · [draw.io](drawio/user-workflow.drawio) |
| Workflow orchestration | Planning, persisted stages, and execution gates | [SVG](svg/workflow-orchestration.svg) · [draw.io](drawio/workflow-orchestration.drawio) |
| Alignment review | Automatic candidates, review export, and accepted overrides | [SVG](svg/alignment-review.svg) · [draw.io](drawio/alignment-review.drawio) |
| AtlasData lifecycle | Proposed, reviewed, and published baseline states | [SVG](svg/atlasdata-lifecycle.svg) · [draw.io](drawio/atlasdata-lifecycle.drawio) |
| Multi-part composition | Parts, annexes, family composition, and downstream exports | [SVG](svg/multipart-composition.svg) · [draw.io](drawio/multipart-composition.drawio) |

## Persistence, publication, and exports

| Diagram | Purpose | Files |
|---|---|---|
| Artifact lineage | Provenance across extracted, normalized, aligned, and exported artefacts | [SVG](svg/artifact-lineage.svg) · [draw.io](drawio/artifact-lineage.drawio) |
| Workspace layout | Relationship between private `.atlas`, versioned data, and generated outputs | [SVG](svg/workspace-layout.svg) · [draw.io](drawio/workspace-layout.drawio) |
| Content boundary | Separation of licensed source content from publishable structural knowledge | [SVG](svg/content-boundary.svg) · [draw.io](drawio/content-boundary.drawio) |
| Doorstop hierarchy | Parent-child hierarchy for standard families and parts | [SVG](svg/doorstop-hierarchy.svg) · [draw.io](drawio/doorstop-hierarchy.drawio) |

## ADR-specific diagrams

| ADR | Diagram | Files |
|---|---|---|
| ADR 0002 | Traceability-centric architecture | [SVG](svg/adr-0002-traceability.svg) · [draw.io](drawio/adr-0002-traceability.drawio) |
| ADR 0003 | Hexagonal architecture | [SVG](svg/adr-0003-hexagonal.svg) · [draw.io](drawio/adr-0003-hexagonal.drawio) |
| ADR 0004 | Transformation pipeline | [SVG](svg/adr-0004-pipeline.svg) · [draw.io](drawio/adr-0004-pipeline.drawio) |
| ADR 0006 | Canonical representation | [SVG](svg/adr-0006-canonical.svg) · [draw.io](drawio/adr-0006-canonical.drawio) |
| ADR 0007 | Source provenance | [SVG](svg/adr-0007-provenance.svg) · [draw.io](drawio/adr-0007-provenance.drawio) |
| ADR 0014 | Alignment review files | [SVG](svg/adr-0014-review-files.svg) · [draw.io](drawio/adr-0014-review-files.drawio) |
| ADR 0025 | AtlasData compatibility | [SVG](svg/adr-0025-compatibility.svg) · [draw.io](drawio/adr-0025-compatibility.drawio) |
| ADR 0026 | NormalizedDocument contract | [SVG](svg/adr-0026-normalized-contract.svg) · [draw.io](drawio/adr-0026-normalized-contract.drawio) |

## Export convention

When exporting from draw.io:

1. preserve the diagram's page size;
2. crop to content;
3. include embedded fonts only when license-compatible;
4. keep text selectable in the SVG;
5. overwrite the corresponding file under `svg/`;
6. verify that Markdown renders correctly in both light and dark GitHub themes.

[Back to architecture](../README.md) · [Back to documentation home](../../README.md)
