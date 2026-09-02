# Prompt workbench

The prompt workbench is a transport-neutral application capability for reproducible,
single-clause prompt experiments. It is deliberately not a conversational history model:
each run binds one packaged or edited prompt, one persisted clause, one explicit context
variant, one manifest-declared model, and one structured output schema.

## Application boundary

`application.prompt_workbench` owns:

- exact clause resolution by stable ID, qualified reference key, or unique human reference;
- discovery contracts for packaged prompts and manifest-declared RamaLama models;
- task-aware assembly of CBox, structural, routing-source, and context-free inputs;
- validation and compilation of editable prompt templates;
- construction and execution of one provider-neutral structured-generation request;
- complete Draft 2020-12 validation of the generated JSON object.

The application service depends on `ClauseProvider`, `LlmGateway`, `PromptCatalog`, and
`ModelCatalog`. It does not start or stop RamaLama, host HTTP, read arbitrary paths, or write
results into an `EngineeringDocument`.

## Context variants

The public catalog exposes the existing versioned CBox frames plus three workbench variants:

| Variant | Intended use |
|---|---|
| `none` | Content-only prompts and isolation tests. |
| `full-context-v1` | Complete qualification-compatible CBox projection. |
| `applicability-minimal-v1` | Clause identity and heading without broader routing evidence. |
| `applicability-isolated-v1` | Clause identity only. |
| `structural-context-v1` | Role prompts using deterministic structure and metadata. |
| `routing-source-v1` | Context-routing enrichment before interpreted routing exists. |

Every assembly also provides the stable template variables `content`, `text`, `reference`,
`content_hash`, `metadata`, `structural_context`, `context_json`, and `context_text`.
Selecting a variant does not silently rewrite a prompt; clients can inspect the placeholders
actually used by the current template.

## Resource adapters

`ResourcePromptCatalog` discovers only complete prompt bundles containing `prompt.json`,
`schema.json`, `system.txt`, and `user.txt`. `ManifestRamaLamaModelCatalog` reads qualification
matrix manifests, filters RamaLama candidates, deduplicates identical declarations, retains
their source manifests, and rejects conflicting model references.

The later web slice is an inbound adapter around this boundary. RamaLama lifecycle
serialization, local HTTP security, experiment persistence, and browser rendering remain
outside the headless core.
