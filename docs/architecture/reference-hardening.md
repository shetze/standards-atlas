# Reference hardening

Standards Atlas preserves structural reference evidence before taxonomy or ontology
interpretation. Reference extraction is deterministic and high-recall: explicit clause,
subclause, paragraph and section references are retained even when they cannot yet be
resolved. Contextual expressions such as `this clause`, `the following clauses`, and
`the preceding clauses` are persisted with direction/cardinality hints and a deferred
resolution status.

`Clause.reference_mentions` is therefore evidence, not semantic interpretation. The
next taxonomy stage may turn these mentions into structural graph edges; the ontology
stage may later determine the meaning of those relations.

Resolved internal references are rendered as Markdown links whenever their target is
known. Unresolved or deferred mentions remain plain text and are never silently dropped.
