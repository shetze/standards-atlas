# ADR 0051: Multidimensional semantic classification

## Status

Accepted

## Context

The former `SemanticRole` taxonomy mixed linguistic statement functions, document structure, domain functions, normative status, presentation forms, and references in one flat list. These dimensions depend on different evidence and are not mutually exclusive. Document families outside ISO/IEC standards also require their own structural vocabularies.

## Decision

`Clause.semantic_roles` and `SemanticRole` are removed without a compatibility layer. Every clause owns a `SemanticClassification` with independent dimensions:

- `statement_functions`
- `applicability_functions`
- `responsibility_functions`
- `document_structure`
- `normative_status`
- `domain_functions`
- `relations`

Document structures are qualified by a document family. Domain functions are qualified by a KnowledgeDomain and taxonomy version. Annex position and normative status are represented separately. Relations distinguish their semantic kind from their internal or external scope.

The former `semantic-role-classification` evaluation task becomes `statement-function-classification`. Version 2.0.0 of that task classifies three independent clause-level dimensions: linguistic statement function, scope/applicability function, and responsibility allocation. Structure, status, domain functions, and relation extraction remain separate evaluation concerns.

Resolved internal relations are rendered as Markdown links. Link generation uses relation targets rather than unverified textual pattern matching.

## Consequences

Persisted EngineeringDocument and evaluation artefacts using `semantic_roles` must be regenerated. Existing gold annotations are not migrated automatically. Prompts and metrics can now be developed per semantic dimension without forcing unrelated labels into one taxonomy.


## Supersedes

- ADR 0022: Extensible semantic-role classification
- The temporary `Clause.semantic_roles` compatibility decision in ADR 0050
