# AP03 status — Series A / S01-S02 complete

Date: 2026-10-02. Series A implements only AP03-S01 and AP03-S02 on the supplied start snapshot
`standards-atlas-current-202610021913(1).zip` (SHA-256
`f9545ade7b294bed4423e83ba98410355563a8d0c8ff247a765b20231ab0f898`). AP03 Series B is not
started.

No real model, remote LLM, Codex client or semantic quality experiment was executed. The changes are
contract/preflight/resource work only.

## S01 — inventory, preflight and frozen B0

`docs/development/ap03-consumer-matrix.md` records the inspected direct consumers and assigns deferred
changes to later slices. The supplied snapshot includes the AP02 post-Series-F heading-source and
reverse-reference corrections; Series A treats them as part of B0 and does not replace them with
prompt heuristics.

`resources/semantic/prompts/ap03-b0.json` freezes the post-AP02 reference state before any semantic
prompt optimization. It binds:

- the exact supplied snapshot hash;
- the documented original AP01 audit, Development Golden and v8-report identities/hashes without
  recreating those absent private files;
- extractor and verifier task/prompt/schema resource hashes;
- AP02 source-surface, candidate, selection, source-package, binding and CBox contract identities;
- the declared runtime configuration bytes while explicitly requiring later experiments to bind the
  actually selected/effective model and provider.

`run_ap03_preflight()` and CLI `evaluation assertion-ap03-preflight` provide a text-free, model-free
readiness check. Resolution is limited to registered project roots. The report distinguishes missing,
ambiguous and invalid historical inputs; validates B0 prompt/task/schema/context/config integrity;
lists model *declarations* without claiming availability; and remains `not_ready_for_release` while
quality thresholds, finalist freeze, real measurements and Holdout evidence are absent. It cannot
write Golden or canonical knowledge state.

`docs/development/engineering-extraction-qualification.md` records the minimum experiment-plan and
release-profile information for later slices. Numeric quality gates are intentionally not invented in
Series A.

## S02 — one productive versioned prompt/task/schema path

The current source-bound roles now use the existing prompt repository/catalog instead of owning
independent inline prompt/schema truths:

- extractor task `formal-semantic-knowledge-proposal`, prompt
  `ontology-guided-assertions-source-bound-v1`, task schema `1.0.0`;
- verifier task `formal-semantic-assertion-verification`, prompt
  `ontology-guided-assertion-verifier-source-bound-v1`, task schema `1.0.0`.

`PromptRepository` rejects incomplete bundles, task/version identity mismatches, missing task
resources and any divergence between the prompt-local schema copy and the task-owned schema. The
self-contained schema copy remains because the existing Prompt Workbench expects complete bundles;
it is no longer independent schema authority.

Both productive adapters compile through `application/evaluation/source_bound_prompt.py`. The helper
renders exactly the previous `json.dumps(payload, ensure_ascii=False)` B0 request body and records
only additional prompt/task/schema fingerprints in metadata. No second prompt catalog or model
process manager was introduced.

The legacy packaged task `formal-semantic-knowledge-extraction/1.0.0`, whose active contract was
`entities`/`relations`, is removed. The inspected productive source tree has no remaining consumer of
that task. Prompt Workbench context recommendations now point at the current proposal task. Generic
historical string values in domain-model tests are not task-resource consumers and remain untouched.
There is no automatic conversion from old `relations` payloads to assertions.

## B0 request-equivalence evidence

Old and migrated adapters were executed in separate processes against the unchanged start-snapshot
code and the same public synthetic source-bound inputs. For both roles the fields `task`,
`prompt_version`, `model`, `temperature`, `output_schema`, `system_prompt` and `user_prompt` are
equal before and after migration.

- extractor canonical compared-content SHA-256:
  `94307954ab90d59e5c4500e37183d9313699aa16b3df3c76523885c6f106d59a`
- verifier canonical compared-content SHA-256:
  `be470b56106a6b7688c4003de211b3b81418a8452848a3ae19c6a8af42a5ea57`

The only request differences are deliberate metadata additions for task-schema and prompt/schema
fingerprints. These do not change the B0 semantic instructions, output structure or source-package
JSON.

## Historical AP01 inputs

The original private AP01 audit, published Golden and v8 qualification report are still absent from
this supplied snapshot. Series A does not reconstruct them from `ap01-status.md` or other summaries.
Their frozen identities are used only to validate originals if they are later placed in the registered
local review/evaluation areas. Therefore the historical replay and all real B0 measurements remain
not executed.

## Test status

The exact Series-A delivery commands/results are recorded in `_delivery/ap03-series-a/tests.md`.
Public tests use only synthetic fixtures/Fake gateways. The implementation environment has Python
3.13 and pytest available, but `ruff` is not installed. An attempted `uv run pytest ...` could not
resolve dependencies because outbound PyPI/DNS access is unavailable; the project test suite is
therefore also run directly with the already installed Python 3.13 environment. No unavailable check
is reported as passed.

## Handover to Series B

Series B may now add P1/P2 as new, explicitly unqualified prompt variants on the same catalog and
schema/source contract while leaving B0 unchanged. S03 should add the shared R01-R14 fachliche policy
for extractor/verifier roles; S04 should connect Workbench preview/run to the same productive
request/parser/grounding path. It must not reinterpret this Series-A migration as a model-quality
improvement or use the missing AP01 private artifacts as if they had been replayed.
