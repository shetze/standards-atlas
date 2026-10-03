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

## Series-B S03/S04 consumer update

The matrix above remains the Series-A cut-over inventory. Series B resolved its S03/S04 deferred
items without changing later-slice ownership:

| Consumer / boundary | Series-B change | Guard / resulting owner |
|---|---|---|
| `PromptRepository` | Adds optional versioned shared policy and public-synthetic example bindings; B0 bundles with no binding retain their exact effective request. | AP03 prompt-contract tests plus independent start/work B0 probe. S05 consumes the same repository. |
| Extractor prompt | Adds unqualified P1/P2 bundles on the current task/schema/source contract. | No schema/source-policy change, private norm text or Clause-ID special case. S11/S12 own real measurements. |
| Verifier prompt | Adds matching unqualified P1/P2 verifier bundles bound to the identical R01-R14 policy with role-specific omission checking. | Same policy hash as extractor; verifier task/schema remains independent. S13 owns measured verifier quality. |
| Productive knowledge parser | Request construction and output parsing/grounding move from adapter-private helpers into `application/knowledge_proposal_extraction/pipeline.py`. | Productive adapter delegates to the shared functions; no alternate parser or matcher. |
| Prompt Workbench service | Adds AP03 source-bound preview/run that resolves the real EngineeringDocument/source package and calls the shared productive request/parser functions. The generic experiment path rejects the assertion-proposal task. | Preview gateway-call guard; exact Workbench/productive request equality test; no schema-only bypass; S05 remains the experiment-runner owner. |
| Prompt Workbench web/API | Shows exact source package/request and distinct schema/parser/grounding/semantic-quality stages. Browser editing of prompt/schema/context is disabled for the source-bound assertion task. | Schema-valid bad grounding is explicitly non-success; semantic quality is never inferred. Existing non-source-bound/Applicability flow remains. |
| AP02 source contract | Consumed unchanged by both productive extraction and Workbench. | Integration/architecture regression set retains headings, gaps, source refs and multi-span grounding. |
| B0 | No resource modification and no implicit policy/example binding. | Full synthetic `StructuredGenerationRequest` byte equality start vs Series-B tree for both roles. |
| Golden/evaluator/Holdout | No change. | Historical expected content remains untouched; S05+ and S07+ retain ownership. |


## Series-C S05/S06 consumer update

| Consumer / boundary | Series-C change | Guard / resulting owner |
|---|---|---|
| `LlmGateway` | Wrapped only at the AP03 attempt boundary to enforce budgets before calls and capture effective attempt provenance/raw bytes privately. | Existing gateway remains the only model transport; S10 may inspect provider-specific parameter support, not replace this path. |
| `KnowledgeProposalExtractionService` | Reused as the sequential clause runner for every experiment cell. | No second parser/runner; native proposal failures and successes remain the productive contract. |
| Source-package repository | Planning stores/loads the existing immutable AP02 package and binds its hash plus exact rendered request per case. | Source drift blocks before inference. |
| Proposal repository | Successful native clause proposals are persisted through the existing filesystem proposal repository. | Resume/reports reload the same native candidates; no alternate experiment proposal format. |
| Schema governance | Adds central schema-1 families for experiment manifest, public resume state and comparison report. | Architecture/schema tests enforce current/readable versions. |
| `AssertionQualificationEvaluator` | Called unchanged by S06 on persisted native candidates. | No new matcher, fuzzy alignment or diagnostic score path; S11+ supplies real Development candidates. |
| CLI | Adds bounded plan/run/resume/report operations. Plan performs zero model calls; Run/Resume require explicit plan authorization. | No background daemon or model manager. |
| Private raw data | New filesystem experiment repository stores request/raw-response/parser details only below private `.atlas/data/assertion-experiments`. | Public state/report carry hashes/status only; S09 later adds MCP access controls without exposing this private store. |
| Golden/Holdout/review | No contents or publisher changed. | S07/S08 retain corpus/partition/HITL ownership; Series C creates no human semantic decisions. |

## Series-E S09/S10 consumer update

| Consumer / boundary | Series-E change | Guard / resulting owner |
|---|---|---|
| MCP server configuration | Adds a dedicated `ap03-development` profile with non-empty server-owned source/review scope. | Mixed Development/Holdout source clause/group/package overlap fails before serving; general profile remains unchanged. |
| Clause reads/search/sample | Development profile resolves only S08 Development source-surface IDs and searches that in-memory allowed population. | No broad provider enumeration/search; generic CBox/reference routing is stripped from clause payloads. |
| MCP resources/media/formulas | Not registered in the Development profile. | No resource URI, table/formula/media or arbitrary path bypass. |
| Assertion review | Reuses S08 package/state but projects Development cases only. | No Holdout selector, no model write to human state, no Golden publication. |
| Experiment diagnostics | Adds opaque-ID reads for explicitly registered Development manifests/state/comparison. | Partition/data route/cases/source packages are revalidated; private raw paths/messages and arbitrary report paths are not exposed. |
| `mcp probe` | Can bind expected tools/resources/profile to the supplied server config. | Generic server handshake does not stand in for scoped-profile verification. |
| `mcp codex-config` | Can derive `enabled_tools` from the exact configured server profile. | Client allowlist remains an additional fence, never server authorization. |
| Codex optimization handoff | One narrow idempotent proposal stages a `codex-*` role-prompt bundle under a server-owned AP03 local path. | Exact authorized Development manifest, path, data route, cases and budget checked; schema/user/policy/examples inherited and validated; zero inference on submission. |
| Existing experiment runner | Adds explicit bounded staged-prompt repository input for `codex-*` variants. | Plan/Run/Resume remain the existing operations and preserve request-hash/budget/authorization enforcement. |
| Codex client probe | New opt-in probe uses only `get_server_info`, requires explicit model for a real call. | Missing client/approval is `not_executed`; no standards text is used. |
| `CodexCliLlmGateway` | Kept separate from optimizer; direct inference disabled by default. Unsupported decoder controls are rejected and removed from request identity. | Not a controlled AP03 qualification arm; S11/S12 should use the approved experiment model route instead. |
| Golden/evaluator/Holdout | No content or semantic matcher changed. | S11/S12 own real Development measurement; Holdout remains reserved for S15. |
