# ADR 0049: Extract and resolve clause references before semantic evaluation

## Status

Accepted

## Context

Semantic roles often depend on references to other clauses. Asking an LLM to detect,
resolve, and interpret those references in one step makes evaluation less reproducible
and hides whether an error came from syntax detection, document resolution, or semantic
interpretation.

## Decision

Standards Atlas performs deterministic reference extraction before semantic evaluation.
Detected clause and clause-range expressions are resolved only against the clauses of the
same persisted EngineeringDocument. Each occurrence preserves its source span, literal
surface text, resolution status, stable target clause identifiers, readable references,
and unresolved diagnostics.

Reference analyses are stored below `local/evaluation/references/<domain>/<document>/`.
They may contain protected clause context and are therefore not published automatically.
The HITL Markdown export includes available reference analyses as additional evidence.
Semantic relation typing remains a later LLM and review responsibility.

## Consequences

Reference detection and resolution can be tested independently from model quality.
Unresolved and ambiguous expressions remain visible rather than being guessed. Future
metrics can distinguish reference detection, target resolution, and semantic relation
classification. Cross-document, table, figure, and annex references require explicit
future extensions to the contract.
