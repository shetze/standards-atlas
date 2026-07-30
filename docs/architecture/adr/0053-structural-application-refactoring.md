# ADR 0052: Structural application refactoring

## Status

Accepted

## Context

The CLI composition root, end-to-end workflow service, normalization service, and
semantic evaluation package had accumulated multiple independent reasons to
change. This made architectural boundaries harder to see and encouraged further
coupling in already large modules.

## Decision

- The Typer application tree is defined in `standards_atlas.cli.apps`; command
  implementations are grouped below `standards_atlas.cli.commands`.
- Workflow planning, execution, and artifact recovery are separate services.
  `EndToEndWorkflowService` remains a small composition facade.
- Generic model/prompt evaluation is located in `application.evaluation`.
  Standards-specific corpus, annotation, reference, consensus, and qualification
  logic is located in `application.semantic_qualification`.
- Document normalization is orchestrated as an explicit ordered pipeline of
  named transformation steps.

## Consequences

The existing CLI and workflow service APIs remain stable while responsibilities
can be tested and evolved independently. New CLI commands belong in the matching
command module. New normalization transformations must be represented by a
pipeline step, and generic evaluation code must not depend on semantic
qualification services.
