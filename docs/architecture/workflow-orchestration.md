# Workflow orchestration

![Workflow orchestration](diagrams/svg/workflow-orchestration.svg)

The diagram focuses on planner, executor, recovery, reporting, and manual gates. Individual services invoked by the executor, CLI option mapping, runtime leases, and every persisted workflow artifact are described in text rather than shown as separate UML elements.

The workflow subsystem is split into planning, execution, recovery, and reporting.

## Planner

`WorkflowPlanner` resolves catalog intent into an ordered `WorkflowPlan`. Planning is side-effect free. It determines required stages, existing artifacts, replacement policy, manual gates, and selected publication targets. Exactly one document-family selection mode is used for a run.

## Executor

`WorkflowExecutor` executes the plan by invoking focused application services. It does not contain extraction, normalization, alignment, or rendering algorithms. It records stage outcomes and stops at unresolved manual gates. Runtime resources such as a managed local LLM server are acquired only by operations that need them and must be released reliably.

## Recovery

`WorkflowRecovery` inspects incomplete or inconsistent workspace state and derives repair actions. `--overwrite`, `--force`, and stage-specific retention options are explicit user policies; they are not interchangeable. Recovery should prefer the smallest safe invalidation set.

## Reporting

Derivation reports make decisions observable: why a stage ran, why it was reused, which predecessor invalidated it, and where review is required. This report is part of the workflow contract and supports reproducibility and troubleshooting.

## Manual gates

- alignment review;
- generated AtlasData baseline review;
- optional annotation or golden-corpus review;
- future relationship adjudication.

`--continue-after-review` is valid only when the expected reviewed artifact exists and passes its contract.
## Task boundaries

The planner has two explicit task-level semantic boundaries. `--task documents` is the canonical
deterministic document pipeline. It may invoke Docling and deterministic structural-taxonomy
services and may publish Markdown and Doorstop output, but it never schedules an LLM-backed
semantic-profile classifier.

`--task qualification` reuses the required deterministic document stages, then explicitly opts
into `document enrich-semantics`. `SEMANTIC_ENRICHMENT` materializes the accepted production
semantic profile in the canonical EngineeringDocument; it is not a qualification candidate run.
Qualification retains Markdown reference publication but removes Doorstop export/publication from
its derived document plan. Corpus construction, matrix qualification, semantic extraction
qualification, and immutable run archival follow afterwards. Candidate proposals remain in
evaluation artifacts and never write through the semantic enrichment service.

`--limit` applies only to qualification execution. Accepted semantic enrichment remains
document-wide so qualification cannot leave persisted EngineeringDocuments partially enriched.
The enrichment stage uses semantic classification internally and is distinct from the formal OWL
TBox/RBox/ABox/CBox model.

