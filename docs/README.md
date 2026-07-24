# Standards Atlas documentation

Standards Atlas documentation is organized by audience and task. New users should begin with the user guide; contributors and reviewers can move directly to architecture, development, reference material, or the decision record.

## Documentation map

| Area | Purpose | Entry point |
|---|---|---|
| **User guide** | Install, configure, import, review, compose, and export standards. | [Open the user guide](user-guide/README.md) |
| **Architecture** | Understand system boundaries, domain contracts, transformations, persistence, and workflow gates. | [Open the architecture guide](architecture/README.md) |
| **Development** | Navigate the codebase, add adapters or classifiers, and run qualification tests. | [Open the development guide](development/README.md) |
| **Reference** | Look up CLI commands, catalog fields, artefact formats, and terminology. | [Open the reference guide](reference/README.md) |
| **Architecture decisions** | Review the rationale and consequences of important technical decisions. | [Open the ADR index](architecture/adr/README.md) |
| **Diagrams** | Browse reusable SVG diagrams and their editable draw.io sources. | [Open the diagram catalog](architecture/diagrams/README.md) |

## Suggested reading paths

### First successful workflow

1. [Getting started](user-guide/getting-started.md)
2. [Core concepts](user-guide/concepts.md)
3. [Catalogs and profiles](user-guide/catalogs-and-profiles.md)
4. [Document workflow](user-guide/document-workflow.md)
5. [Alignment review](user-guide/alignment-review.md)
6. [Exports](user-guide/exports.md)

### Architecture review

1. [System context](architecture/system-context.md)
2. [Processing pipeline](architecture/processing-pipeline.md)
3. [Domain model](architecture/domain-model.md)
4. [Ports and adapters](architecture/ports-and-adapters.md)
5. [Persistence and lineage](architecture/persistence-and-lineage.md)
6. [Workflow orchestration](architecture/workflow-orchestration.md)
7. [ADR index](architecture/adr/README.md)

### Extending the platform

1. [Project layout](development/project-layout.md)
2. [Extending Standards Atlas](development/extending.md)
3. [Testing and qualification](development/testing-and-qualification.md)
4. [Artifact formats](reference/artifact-formats.md)
5. [CLI reference](reference/cli-reference.md)

## Core user topics

- [Workspace and persisted artefacts](user-guide/workspace.md)
- [AtlasData lifecycle and baseline governance](user-guide/atlasdata-lifecycle.md)
- [Multi-part standards and family composition](user-guide/multipart-standards.md)
- [Troubleshooting](user-guide/troubleshooting.md)
- [Security and copyright boundaries](architecture/security-and-copyright.md)

[Back to the project README](../README.md)
