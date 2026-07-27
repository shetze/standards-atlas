# Evaluation Services

The evaluation application service is intentionally domain-neutral. It supports semantic clause evaluation today, but its contracts are suitable for any versioned prompt, dataset, model, metric, regression, and report workflow.

## Location

The canonical implementation lives in:

```text
src/standards_atlas/application/services/evaluation/
```

The former `application/semantic_evaluation/` package remains as a compatibility facade. New code must import the generic service package.

## Responsibilities

- load versioned prompt definitions and output schemas;
- load versioned evaluation datasets;
- execute a prompt against one or more models;
- compare prompt versions under a fixed model;
- calculate per-case and aggregate metrics;
- detect regressions against a baseline;
- persist machine-readable run and comparison reports.

The service depends only on the `LlmGateway` application port. CLI, future HTTP APIs, and MCP adapters are clients of this service and must not duplicate evaluation logic.

## Terminology

The canonical names are `EvaluationDataset`, `EvaluationExample`, `EvaluationRunner`, `EvaluationReporter`, and `EvaluationDatasetRepository`. The previous `Golden*` and `SemanticEvaluation*` names are aliases during the migration period.

## Local protected corpora

Copyrighted evaluation data belongs below `local/` and remains outside version control. Repositories receive their root path explicitly, so the same service can consume packaged synthetic corpora or local real-world corpora without coupling the application layer to storage policy.
