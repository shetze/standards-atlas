# Evaluation services

Standards Atlas separates reusable evaluation infrastructure from the
standards-specific semantic qualification workflow. The split keeps generic
prompt, dataset, model, metric, regression, and reporting code independent of
clause access, annotation policy, standards taxonomies, and review workflows.

## Package structure

The canonical implementation is divided into two application packages:

```text
src/standards_atlas/application/evaluation/
    Generic evaluation models, repositories, runners, schemas,
    metrics, regression comparison, and reports.

src/standards_atlas/application/semantic_qualification/
    Standards-specific clause access, corpus construction, annotations,
    proposal generation, reference analysis, review, qualification matrices,
    model consensus, and workflow orchestration.
```

A compatibility facade currently remains at:

```text
src/standards_atlas/application/services/evaluation/
```

It re-exports selected types from both canonical packages for callers that have
not yet migrated. New code should import directly from `application.evaluation`
or `application.semantic_qualification`. The facade is not the owner of the
implementation and may be removed after all callers have migrated.

## Generic evaluation responsibilities

The `application.evaluation` package is responsible for:

- loading versioned prompt definitions and output schemas;
- loading versioned evaluation datasets;
- executing prompts against one or more models through the `LlmGateway` port;
- comparing prompt and model configurations;
- calculating per-case and aggregate metrics;
- detecting regressions against a baseline;
- persisting machine-readable runs, comparisons, and reports.

Its canonical vocabulary includes `EvaluationDataset`, `EvaluationExample`,
`EvaluationRunner`, `EvaluationReporter`, `EvaluationDatasetRepository`, and
`PromptRepository`. Historical `Golden*` and `SemanticEvaluation*` names remain
only as migration aliases where required by existing callers or persisted data.

## Semantic qualification responsibilities

The `application.semantic_qualification` package adds the domain-specific
workflow around clauses from persisted `EngineeringDocument` aggregates:

- transport-neutral clause discovery through `ClauseProvider`;
- representative and reproducible corpus construction;
- annotation repositories and publication precedence;
- baseline and model proposal generation;
- clause-reference extraction and resolution;
- human review export and import;
- prompt and model qualification matrices;
- model-consensus calculation and golden-corpus proposals.

These services may depend on the generic evaluation package, but the generic
package must not depend on semantic qualification.

## Dependency direction

```text
CLI / MCP / future API adapters
            |
            v
application.semantic_qualification
            |
            v
application.evaluation -----> LlmGateway port
```

Storage adapters implement repositories and gateways at the boundary. The CLI
acts as the composition root and supplies concrete filesystem repositories,
LLM gateways, and clause providers.

## Local protected corpora

Copyrighted evaluation material belongs below `local/` and remains outside
version control. Repositories receive their root path explicitly, allowing the
same application services to consume packaged synthetic fixtures and protected
local corpora without embedding storage policy in the domain model.
