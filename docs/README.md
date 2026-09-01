# Standards Atlas documentation

The documentation is organized by reader intent: begin using the tool, complete a task, understand the design, contribute code, or look up an exact command or format.

## Start here

| You want to… | Start with |
|---|---|
| Get a first workflow running | [Getting started](getting-started/README.md) |
| Follow a guided learning path | [Tutorials](tutorials/README.md) |
| Complete an operational task | [User guide](user-guide/README.md) |
| Understand system boundaries and contracts | [Architecture](architecture/README.md) |
| Change or extend the code | [Development guide](development/README.md) |
| Look up commands, formats, or terminology | [Reference](reference/README.md) |
| Understand important design decisions | [ADR index](architecture/adr/README.md) |
| See current and planned direction | [Project direction](roadmap/README.md) |

## Documentation model

The project follows four complementary documentation modes:

- **Getting started and tutorials** teach through ordered learning paths.
- **User guides** explain how to complete concrete engineering tasks.
- **Architecture and development guides** explain design, constraints, contribution workflows, and extension points.
- **Reference material** provides concise lookup information without repeating rationale.

## Recommended paths

### First successful workflow

1. [Getting started](getting-started/README.md)
2. [Core concepts](user-guide/concepts.md)
3. [Catalogs and profiles](user-guide/catalogs-and-profiles.md)
4. [Document workflow](user-guide/document-workflow.md)
5. [Workspace](user-guide/workspace.md)
6. [Exports](user-guide/exports.md)

### Architecture review

1. [System context](architecture/system-context.md)
2. [Processing pipeline](architecture/processing-pipeline.md)
3. [Domain model](architecture/domain-model.md)
4. [Ports and adapters](architecture/ports-and-adapters.md)
5. [Persistence and lineage](architecture/persistence-and-lineage.md)
6. [Evolution and compatibility](architecture/evolution-and-compatibility.md)
7. [Workflow orchestration](architecture/workflow-orchestration.md)
8. [Relationship-mapping target architecture](architecture/relationship-mapping.md)
9. [ADR index](architecture/adr/README.md)

### Governance and compliance integration

1. [Exports](user-guide/exports.md)
2. [Gemara and ComplyTime integration](user-guide/gemara-complytime.md)
3. [Artifact formats](reference/artifact-formats.md)
4. [Ports and adapters](architecture/ports-and-adapters.md)
5. [Persistence and lineage](architecture/persistence-and-lineage.md)

### Evaluation and model-assisted review

1. [Evaluation and qualification](user-guide/evaluation-and-qualification.md)
2. [Model consensus evaluation](user-guide/model-consensus-evaluation.md)
3. [Semantic annotation review](user-guide/semantic-annotation-review.md)
4. [Evaluation services](architecture/evaluation-services.md)
5. [Evaluation clause access](architecture/evaluation-clause-access.md)
6. [Testing and qualification](development/testing-and-qualification.md)

### Contributor onboarding

1. [Contributing](../CONTRIBUTING.md)
2. [Project layout](development/project-layout.md)
3. [Extending Standards Atlas](development/extending.md)
4. [Testing and qualification](development/testing-and-qualification.md)
5. [Architecture principles](architecture/principles.md)

## Documentation boundaries

Each maintained fact has one canonical home. Audience-specific pages should link to that source rather than copying it. Historical implementations are kept under [History](history/) and must state that they are not current product references. Documentation authoring rules are defined in the [documentation style guide](development/documentation-style-guide.md).

## Maintainer resources

- [Diagram catalog](architecture/diagrams/README.md)
- [Security and copyright boundaries](architecture/security-and-copyright.md)
- [Evolution and compatibility policy](architecture/evolution-and-compatibility.md)
- [Release and versioning](development/release-and-versioning.md)
- [Artifact formats](reference/artifact-formats.md)
- [Glossary](reference/glossary.md)
- [Roadmap and next steps](roadmap/README.md)
- [Engineering methodology](methodology/README.md)
- [Documentation style guide](development/documentation-style-guide.md)

[Back to the project README](../README.md)

## Historical rationale

- [Evolution of the semantic evaluation model](history/semantic-evaluation-model-evolution.md)
- [Legacy relationship-mapping prototype](history/legacy-relationship-mapping.md)
