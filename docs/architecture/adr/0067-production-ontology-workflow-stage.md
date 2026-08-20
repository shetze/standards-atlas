# ADR 0067: Production ontology workflow stage

## Status

Accepted

## Decision

The document workflow executes semantic ontology classification in a dedicated
`ONTOLOGY` stage immediately after deterministic `TAXONOMY` classification.

The ontology stage consumes canonical clause content plus the materialized
`StructuralContext`, structural profile, contextual ancestor content, and persisted
reference mentions. It does not reconstruct document structure from prose.

Production ontology classification uses the ontology application contracts introduced
by ADR 0065. A schema-constrained `LlmOntologyClassifier` implements the production
classifier port and is selected independently from semantic qualification. Qualification
may compare models, prompts, repetitions, consensus, and HITL evidence; production uses
one explicitly selected qualified classifier.

The stage owns these semantic ontology dimensions:

- statement functions;
- knowledge kinds;
- process functions;
- applicability functions;
- responsibility functions.

Existing structural and reference information is preserved. Legacy deterministic
semantic evidence may still exist until the cleanup slice, but the production ontology
stage is authoritative for the five ontology dimensions above.

## Consequences

- Taxonomy must complete before ontology classification can run.
- Production inference can use structural context without coupling the ontology engine
  to the taxonomy implementation.
- Ontology vocabularies remain independently versioned and validated.
- Qualification and production classification share contracts but remain separate use
  cases.
- Removing the remaining deterministic semantic classifier is a subsequent cleanup
  change rather than part of this behavioral slice.
