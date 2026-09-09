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

`documents` owns deterministic document construction, taxonomy and configured Markdown/Doorstop
publication. `qualification` adds contextual enrichment, a reproducible corpus, the qualification
matrix and configured detail/policy/extraction stages before immutable archival. Qualification
candidate artifacts do not implicitly update canonical semantic fields or public companions.

`knowledge` explicitly restores/adopts/publishes already available knowledge without inference.
`enrichments` composes document preparation and qualification with verified archive adoption,
public/private transfer, reimport and a CBox report. Its default starts after Docling and processes
all eligible clauses of the selected physical documents. Source-only corpus context prevents
accepted semantic output from becoming self-feedback on the next run. Every selected document's
structure is prepared before contextual enrichment. Open review gates and technical failures block
publication. Context response validation remains strict, but individual invalid responses are
reported rather than stopping baseline collection. `--fail-on-context-failure` opts into the
previous strict document-level exit. Invalid values are never merged; retained older values are
explicitly distinguished from newly successful attempts. Existing tasks keep their previous
non-publication/opt-in contracts.

Private last-attempt ledgers distinguish succeeded/reused/protected/failed/not-candidate clauses.
Incomplete context checkpoints are revisited; the service reuses successful clauses but does not
use a retained older value to conceal a failed attempt. Baseline archival occurs after context
and after final publication, before ordinary run reporting. It freezes selected source/code/config,
canonical and diagnostic state; the published phase also includes companions, referenced private
blobs and the exact qualification archive. It uses unique private ZIPs outside disposable work
state. Baseline completion is explicitly not semantic verification.

The new task is implemented in `EnrichmentsWorkflowPlanner`, reusing
`QualificationWorkflowPlanner` and the existing workflow service/executor. The CLI injects an
in-process command runner: focused commands retain parameter parsing, service construction and
persistence ownership without CLI subprocess orchestration. Archive handoff uses a checksummed,
matrix-verified receipt rather than a mutable run directory or a global latest-archive lookup.

See the [enrichments workflow guide](../user-guide/enrichments-workflow.md) for execution,
coverage, checkpoint/review behavior and artifact locations.
