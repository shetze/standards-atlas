# ADR 0062: Separate semantic taxonomies from semantic tasks

## Status

Accepted

## Context

Semantic task resources historically embedded `taxonomy.yaml` beside `task.yaml` and
`schema.json`. That coupled the lifecycle of independent label spaces to one evaluation
task version and made the multidimensional 2.x task misleadingly retain the name
`statement-function-classification`.

Statement functions, knowledge kinds, process functions, applicability functions, and
responsibility functions evolve independently and may be reused by future focused tasks.

## Decision

Store semantic label spaces under `resources/semantic/taxonomies/<taxonomy>/<version>`.
Each taxonomy declares its own id, version, output dimension, values, optional semantics,
and optional stable public codes.

Semantic tasks contain references to those independently versioned taxonomies. The task
repository resolves and composes them at load time; task schemas remain the canonical
structured-output contract.

The multidimensional 2.x task is canonically named `semantic-profile-classification`.
`statement-function-classification` remains an explicit compatibility alias for existing
2.x manifests, datasets, prompts, and persisted runs. Version 1.0.0 remains a genuine
statement-function task.

Prompt and dataset repositories may resolve the canonical 2.x task through legacy
resource locations during the compatibility period. New qualification manifests use the
canonical task name.

## Consequences

- one semantic dimension can be versioned without incrementing unrelated taxonomies;
- focused future tasks can reuse the same taxonomy versions without duplication;
- task names describe the semantic operation rather than acting as taxonomy containers;
- the historic 1.0 taxonomy mismatch is removed: `statement-functions/1.0.0` follows the
  actual task schema instead of obsolete structural-role labels;
- legacy 2.x task names continue to load, but new configuration should use
  `semantic-profile-classification`;
- task-local `taxonomy.yaml` files are obsolete and are removed by the Slice 2 migration.

## Related decisions

- ADR 0051: Multidimensional semantic classification
- ADR 0054: Model engineering knowledge as an orthogonal ontology
- ADR 0061: Modular deterministic structural-taxonomy engine
