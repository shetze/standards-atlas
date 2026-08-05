# ADR 0053: Structural application refactoring

## Status

Accepted

## Context

The CLI composition root, end-to-end workflow service, normalization service, and
semantic evaluation package had accumulated multiple independent reasons to
change. This made architectural boundaries harder to see and encouraged further
coupling in already large modules.

## Decision

- The Typer application tree is defined in `standards_atlas.cli.apps`; command
  implementations are grouped below `standards_atlas.cli.commands`. Large command
  families may be split into nested command packages while `cli.composition` remains
  the composition root for concrete adapters.
- Workflow planning, execution, artifact recovery, and derivation reporting are
  separate services below `application.workflow`. `EndToEndWorkflowService` remains
  a small composition facade.
- Generic model/prompt evaluation is located in `application.evaluation`.
  Standards-specific corpus, annotation, reference, consensus, review, and matrix
  qualification logic is located in `application.semantic_qualification`.
- Extraction/normalization qualification against checked-in golden corpora remains a
  separate capability below `application.qualification`; it is not semantic model
  qualification.
- Document normalization is orchestrated as an explicit ordered pipeline of named
  transformation steps below `application.normalization`.
- Cross-cutting use cases that do not yet justify a dedicated capability package may
  remain below `application.services`. Application-owned repository abstractions live
  below `application.repositories`, and lightweight command objects below
  `application.commands`. These packages are ownership boundaries, not permission to
  bypass ports or import adapters.

## Consequences

The existing CLI and workflow service APIs remain stable while responsibilities
can be tested and evolved independently. New CLI commands belong in the matching
command module. New normalization transformations must be represented by a pipeline
step, and generic evaluation code must not depend on semantic qualification services.
Compatibility re-exports may exist for already published imports, but they do not
define canonical ownership and must not be used by new code.
