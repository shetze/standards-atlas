# AP03 status — Series B / S01-S04 complete

Date: 2026-10-02. Series B implements only AP03-S03 and AP03-S04 on the locally checked
post-Series-A snapshot `standards-atlas-current-202610022028.zip` (SHA-256
`4d65d419625e0b9411edf5348b3691773d80536c53b2618c1c3fff320f49e847`). Series A remains the
technical baseline described below. AP03 Series C is not started.

No real model, remote LLM, Codex client, private standards corpus or semantic quality experiment was
executed in Series B. All generation behavior in tests uses Fake gateways and public synthetic text.
P1/P2 are explicitly **unqualified** Development variants; they are not a recommendation for a
model or a claim of improved extraction quality.

## S03 — shared engineering policy and bounded prompt variants

The current extractor and verifier remain separate roles on their existing source-bound task/schema
contracts, but both can now bind the same versioned fachliche policy resource:

- policy `engineering-assertion-extraction@1.0.0` contains a concise R01-R14 implementation covering
  engineering meaning, first-class Work Products, requirement-to-Work-Product relations, Records,
  closed-ontology typing, source-supported assertions, list granularity, Notes/Examples,
  definition/entity-only cases, conditions/exceptions, justified structural interpretation,
  normative Force, Evidence semantics and local identity;
- P1 extractor `engineering-policy-v1` and verifier `engineering-policy-verifier-v1` use that policy
  with role-specific instructions;
- P2 extractor `engineering-policy-contrast-v1` and verifier
  `engineering-policy-verifier-contrast-v1` use the identical policy plus the public-synthetic
  `engineering-contrast@1.0.0` Development example set;
- `resources/semantic/experiments/ap03-engineering-prompt-variants-v1.json` binds B0, P1, P2,
  policy/example hashes, partition and the no-schema/no-source-policy-change constraints.

`PromptRepository` resolves these optional shared bindings from the existing semantic resource tree
and records policy/example identity in generation metadata. It rejects missing or mismatched
resources and accepts example bindings only when they declare a non-empty partition and
`source_class: public_synthetic`. Bundles without these bindings are unchanged.

No private norm text, confirmed Golden expected content or concrete Golden Clause ID is embedded in
these prompt resources. There is no new ontology vocabulary, alias matcher, schema version or
Clause-ID-specific branch.

### B0 remains unchanged

The frozen `resources/semantic/prompts/ap03-b0.json` bytes are unchanged (SHA-256
`888622019e6339379a470dccdf498109b5b1be162197ffbe4324a9b9989bb92a`). In addition to the Series-A
content comparison, Series B executed the same synthetic B0 request probe in separate Python
processes against the supplied start tree and the modified tree. The complete serialized
`StructuredGenerationRequest` is byte-identical for both source-bound roles:

- extractor request SHA-256: `6a129e7a355a7fc67b1d7b86a11184d06d150534b74bbf148d3fc966a52c1706`;
- verifier request SHA-256: `716b230766e6b6d0d5d7bb63fd488fb9288c292c866c2832bc5aa3f95834b789`.

The comparison includes task, prompt version, model/parameter defaults, system/user prompt, schema
and request metadata. Policy/example metadata is added only for prompt variants that actually bind
those resources.

## S04 — Prompt Workbench on the productive source/parser/grounding path

The productive knowledge extractor is internally split into two application-level operations:

1. `prepare_knowledge_proposal_request()` builds the exact AP02 source-bound payload, ontology
   vocabulary, source-package binding and versioned structured-generation request;
2. `parse_knowledge_proposal_result()` applies the productive closed-ontology validation,
   multi-span Evidence parsing/grounding, deterministic local IDs, violations and proposal
   provenance.

`OntologyGuidedKnowledgeProposalExtractor` is now a thin adapter over those operations. The AP03
source-bound Workbench path uses the **same** functions. There is no Workbench-specific assertion
extractor, ontology validator or grounder.

The headless service and web API add separate source-bound endpoints for knowledge extraction:

- preview resolves the real `EngineeringDocument`, constructs the productive AP02 source package,
  interpretation context and exact effective request without calling the gateway;
- run is explicit, executes that exact request once and then reports JSON-Schema validation,
  productive parser result and grounding/ontology violations as separate stages;
- a schema-valid result with invalid Evidence is therefore not a technically valid proposal and is
  never presented as semantic success;
- semantic quality remains `semantic_quality_assessed: false`; Series B does not invoke the Golden
  evaluator or infer quality from schema/grounding success.

For this source-bound mode, the browser no longer owns editable system prompt, user template,
schema or ad-hoc context text. It selects a versioned bundle and parameters, displays the exact
compiled request/source package, and keeps source offsets/source ownership unchanged. The generic
`/api/experiments`/service path explicitly rejects `formal-semantic-knowledge-proposal`, so a caller
cannot bypass the productive parser/grounding route with a hand-built generic request. Generic
historical Workbench behavior remains available for the existing non-source-bound tasks, including
Applicability; the clean assertion path does not reintroduce legacy classification.

The source-bound preview exposes target/heading/context surfaces, selection gaps, omitted sources,
budget and effective request data from the same source package supplied to productive extraction.
Heading-only parent context and unresolved-source diagnostics are retained. Text-release protection
continues to be owned by the existing local Workbench surface; Series B does not create a new remote
or MCP text route.

## Historical AP01/AP02 protection status

Series B does not modify or reconstruct historical AP01 audit bytes, v8 proposals, confirmed Golden
IDs/`expected` contents or the clause-local evaluator. The private AP01 originals remain absent from
this snapshot and were not replayed. AP02 source-package identities, heading ownership,
reverse-reference protections and multi-span grounding remain the technical source contract.

No Golden publisher, `DocumentKnowledge` adoption, Holdout selection, experiment runner, MCP scope,
Codex workflow or Series-C functionality is introduced.

## Test status

The Series-B delivery report records exact commands and outputs. The implementation checks completed
in this environment are:

- targeted S03/S04 unit/adapter/Workbench/architecture set (final): 73 passed;
- AP02 source-bound/workflow integration plus full architecture, schema and filesystem contract set
  (final focused series check): 508 passed;
- Prompt-Workbench CLI surface check: 6 passed;
- JavaScript syntax check for the Workbench client: passed;
- independent start-vs-work B0 request byte comparison: passed for extractor and verifier.

`uv run ruff check .` was attempted but could not create/resolve the project environment because this
execution environment has no working DNS/PyPI access; dependency resolution failed (the final
attempt stopped while fetching `click`, an earlier attempt while fetching `docling`). No Ruff result
is therefore claimed. An additional attempt to run the entire `tests/integration`
tree exceeded the 120-second execution limit after 41 reported tests (two skipped); it is recorded
as incomplete, not failed or passed. The focused source-bound/workflow integration set was then
rerun successfully with the complete architecture/schema/contract set above. The full project
`pytest` suite was not executed here; the user will run Ruff and full pytest after applying the
cumulative delta, as required by the series workflow.

No real model/client run was performed. No test result is reported as a semantic model-quality
measurement.

## Series-A baseline retained

Series A established the AP03 consumer matrix, model-free preflight, experiment/release contract,
frozen B0 reference and one productive versioned task/prompt/schema path. Its current source-bound
roles remain:

- extractor task `formal-semantic-knowledge-proposal`, B0 prompt
  `ontology-guided-assertions-source-bound-v1`, task schema `1.0.0`;
- verifier task `formal-semantic-assertion-verification`, B0 prompt
  `ontology-guided-assertion-verifier-source-bound-v1`, task schema `1.0.0`.

The old active `formal-semantic-knowledge-extraction` entities/relations task remains removed and no
compatibility reader/writer was reintroduced.

## Handover to Series C

Series C may build S05/S06 on this stable path: versioned B0/P1/P2 variants, exact productive
request preparation, explicit run, productive parser/grounding and stage-aware Workbench results are
available. Series C must introduce bounded plan/run/resume and diagnostics in the existing
qualification/workflow framework rather than turning the Workbench into a second runner or matcher.
It must continue to use Fake gateways for implementation tests and must not treat P1/P2 as qualified
or start real experiments without the separately required plan/data/budget approval.
