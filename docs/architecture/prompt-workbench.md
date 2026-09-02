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
`ModelCatalog`. It does not host HTTP, read arbitrary paths, or write results into an
`EngineeringDocument`.

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

## Local web adapter

The `adapters.web` package wraps the headless application capability with a Starlette API and
packaged, dependency-free browser client. It exposes prompt/model/context catalogs, clause
search and exact resolution, context previews, explicit model activation, and experiment
execution. The browser can edit both prompt texts and the output schema before a run.

The CLI requires the service implementation to be named explicitly:

```bash
uv run standards-atlas chat serve --service prompt-workbench
```

`chat serve` is the extensible command family; `prompt-workbench` is one registered service
type rather than an implicit default. `--service-type` is accepted as an alias. New chat
services can therefore receive separate composition functions while sharing the foreground
server entry point.

The HTTP service is deliberately local: configuration rejects non-loopback bind addresses,
requests require a loopback `Host` and (when supplied) `Origin`, bodies are capped at 1 MiB,
and browser responses carry a restrictive Content Security Policy. There is no remote access,
authentication, TLS termination, or multi-user isolation contract in this slice.

## RamaLama coordination

`ManagedRamaLamaGateway` serializes model activation and structured generation with one
process-local lock. If a requested model is not active, it stops only the runtime referenced by
the project ownership record, starts the selected manifest model, waits for readiness, and
performs inference without releasing the lock. Interactive runs bypass the response cache by
default; the request must opt into reuse explicitly.

Experiment persistence and comparison histories remain a later slice. The current endpoint
returns full compilation, validation, generation, and hash provenance to the caller without
mutating an `EngineeringDocument`.
