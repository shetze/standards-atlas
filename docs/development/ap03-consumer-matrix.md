# AP03 Series A consumer matrix

Date: 2026-10-02. This matrix records the directly inspected consumers for AP03-S01/S02. It is a
cut-over inventory, not a claim that later AP03 slices are implemented.

## Baseline identity

- supplied start snapshot: `standards-atlas-current-202610021913(1).zip`
- logical snapshot name used by the AP03 plan: `standards-atlas-current-202610021913.zip`
- SHA-256: `f9545ade7b294bed4423e83ba98410355563a8d0c8ff247a765b20231ab0f898`
- frozen current-model baseline: `B0-AP02`
- no real model/client run is part of Series A

## Consumer matrix

| Consumer / boundary | Start state | Series-A decision | Direct implementation / guard | Next AP03 owner |
|---|---|---|---|---|
| `OntologyGuidedKnowledgeProposalExtractor` | Task `formal-semantic-knowledge-proposal`; output schema and system prompt owned inline by the adapter. | Keep task and source-bound AP02 payload unchanged; move prompt/schema ownership into the existing versioned resource path. | `application/evaluation/source_bound_prompt.py`; `resources/semantic/prompts/formal-semantic-knowledge-proposal/...`; task resource `1.0.0`; adapter tests. | S03 may introduce P1/P2 without changing B0. |
| `OntologyGuidedAssertionProposalVerifier` | Task `formal-semantic-assertion-verification`; separate inline schema and prompt. | Same cut-over as extractor, with verifier role remaining independent. | Versioned verifier prompt/task resources; shared request compiler; verifier tests. | S03 binds a common *fachliche* policy, not a common task instruction. |
| AP02 source-package contract | Productive request contains the selected immutable package, allowed ontology vocabulary and source binding. | Preserve request payload, source identities, multi-span grounding and context selection exactly for B0. | Frozen `ap03-b0.json`; unchanged AP02 package builders; request-content comparison against start snapshot. | S04 Workbench; S05 experiment runner. |
| `PromptRepository` | Loads self-contained prompt bundles; no task-schema cross-check. | A prompt may bind an existing semantic task schema; prompt-local schema is accepted only when semantically equal to task-owned schema. | Optional `PromptDefinition.task_schema_version`; bundle completeness and task/schema validation. | Used by S03/S04 and later experiment variants. |
| `ResourcePromptCatalog` | Existing common catalog for the Prompt Workbench. | Reuse unchanged catalog surface; no AP03 parallel catalog. | It inherits the stricter `PromptRepository` binding. | S03/S04. |
| Prompt Workbench context recommendations | Recommended legacy `formal-semantic-knowledge-extraction` task. | Recommend the current source-bound proposal task. | `application/prompt_workbench/context.py`; architecture guard. | S04 connects preview/run to the productive request/parser path. |
| Legacy semantic task resource | `formal-semantic-knowledge-extraction/1.0.0` describes `entities` + `relations` and a single-string evidence shape. | Remove it as an active production/workbench task after consumer inspection; do not translate it into current assertions. | Task directory deleted; stale domain-test provenance is updated to the current task identity; architecture guards reject a production return of the legacy task. | None; Clean Break. |
| Current semantic task resources | No packaged task resource for current extractor/verifier task IDs. | Add one schema-1 task resource for each current role; schemas equal their B0 prompt schema. | `resources/semantic/tasks/formal-semantic-{knowledge-proposal,assertion-verification}/1.0.0/`. | S03+ variants continue to bind these output contracts unless explicitly versioned. |
| Gateway / `StructuredGenerationRequest` | Existing gateway carries task, prompt version, model, temperature, schema, prompts and metadata. | Do not create another gateway. Add prompt/task/schema fingerprints only to metadata. | Shared request compiler. | S05 records effective runtime/attempt data. |
| `AssertionQualificationEvaluator` | Existing clause-local AP01 evaluator is authoritative for semantic Golden metrics. | No changes and no new matcher. | S01/S02 tests do not modify evaluator behavior. | S06 consumes it; S11+ runs it on real candidates. |
| AP01 private v8 audit / Golden / report | Historical hashes documented; files absent from supplied snapshot. | Do not reconstruct, relabel or overwrite. Preflight resolves only registered project roots and reports absence explicitly. | `run_ap03_preflight`; B0 historical references. | S11 requires originals for real historical replay. |
| AP02 Heading / reverse-reference corrections | Present in the supplied snapshot. | Treat as B0 context contract; no heading promotion or context-scope change. | B0 context fingerprints/contracts; existing AP02 regressions. | S03+ prompts consume, but do not redefine, this source behavior. |
| Model configuration | `cfg/llm.yaml` and qualification manifests declare routes/models; declaration is not availability. | Display declarations model-free and mark availability unverified. Do not infer effective runtime identity from model name. | Preflight report. | S05/S10 establish effective parameter/client provenance. |
| CLI | No AP03 preflight command. | Add a thin read-only JSON preflight command; it performs no inference or download. | `evaluation assertion-ap03-preflight`. | S05 adds execution operations only when implemented. |
| Release/qualification state | No AP03 release contract. | Prepare the contract and always return `not_ready_for_release` while gates/real evidence are open. | `engineering-extraction-qualification.md`; preflight blockers. | S14 freezes approved gate values; S15 evaluates Holdout. |
| Golden / `DocumentKnowledge` writers | Existing AP01/review/adoption boundaries. | No Series-A write path and no automatic human decision. | Preflight flags `golden_or_knowledge_write: false`; no writer changes. | S07/S08 review; AP04 adoption remains separate. |

## B0 request-content proof

The old start-snapshot adapter and the migrated Series-A adapter were executed in separate Python
processes with the same public synthetic source-bound inputs. The comparison intentionally excludes
new provenance-only metadata and compares the fields that determine the structured model request:
`task`, `prompt_version`, `model`, `temperature`, `output_schema`, `system_prompt` and `user_prompt`.

| Role | Start vs migrated content | Canonical comparison SHA-256 |
|---|---|---|
| Extractor | equal | `94307954ab90d59e5c4500e37183d9313699aa16b3df3c76523885c6f106d59a` |
| Verifier | equal | `be470b56106a6b7688c4003de211b3b81418a8452848a3ae19c6a8af42a5ea57` |

The migrated requests additionally record task-schema and prompt/schema fingerprints in request
metadata. These are deliberate provenance additions; they do not alter B0 instructions, schema or
source-bound request JSON.

## Explicit non-consumers / deferred work

Series A does not change the clause-local evaluator, matching policy, ontology vocabulary, context
selection policy, grounding rules, cascade policy, review publisher, MCP server, Codex gateway,
canonical `DocumentKnowledge`, RAG/GraphRAG or model process management. Those boundaries remain
owned by later slices where the AP03 plan assigns them.
