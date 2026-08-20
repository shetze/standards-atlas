# ADR 0069: Materialize structural scope reach in taxonomy

## Status

Accepted

## Context

Standards use `scope` outside dedicated Scope chapters. Such statements often declare
that the current clause, a number of following or preceding sibling clauses, or a
heading-defined subtree shares a common applicability context. This is structural
evidence even when the applicability semantics cannot yet be determined.

Treating these statements only as ontology input loses deterministic information about
the document region to which the statement can apply. Conversely, assigning an
applicability meaning in the taxonomy would cross the taxonomy/ontology boundary.

## Decision

The structural taxonomy records high-recall scope mentions and their structural reach.

`StructuralContext` therefore carries:

- `scope_mentions`, preserving the source text, source location class, direction and
  optional cardinality;
- `scopes`, materializing resolved or deferred edges from the source clause to the
  structurally affected clauses.

The taxonomy resolves only structure-derived reach:

- `this clause` resolves to the current clause;
- `following N clauses` and `preceding N clauses` resolve to sibling clauses;
- headings containing `scope` resolve to the node's descendant subtree;
- open-ended or otherwise ambiguous scope statements remain deferred.

The ontology stage receives these fields as evidence and remains responsible for
interpreting the actual applicability semantics, restrictions, conditions or
exceptions.

## Consequences

Scope statements no longer disappear when they occur outside canonical Scope sections.
The ontology can distinguish semantic applicability interpretation from deterministic
structural reach, and unresolved scope reach remains explicit rather than being guessed.
