# ADR 0046: Persist resumable semantic proposal runs

## Status

Accepted

## Context

Semantic-role baseline proposals require many provider calls and must remain auditable. A proposal alone is insufficient to diagnose prompt, provider, parsing, or schema problems. The same orchestration must support local OpenAI-compatible models and Codex without coupling application services to either runtime.

## Decision

Standards Atlas treats `LlmGateway` as the provider-independent structured-generation port. Baseline proposal generation persists one directory per clause containing the rendered request, the provider response, and the validated proposal. A run summary records generated, skipped, and failed cases.

Task definitions, taxonomy, canonical output schema, and prompt variants are versioned resources. Prompt schemas must equal the canonical task schema before a run starts.

Proposal generation is resumable. Existing proposal annotations are skipped unless the caller explicitly requests overwrite. Provider failures are recorded per case and do not discard successful cases.

RamaLama uses the existing OpenAI-compatible gateway. Codex is supported through a dedicated CLI gateway that invokes schema-constrained `codex exec` and captures the final structured message.

All generated requests, responses, and proposals remain under `local/evaluation`. Publication and human review remain separate lifecycle steps.

## Consequences

- LLM calls are reproducible and auditable.
- Parser or prompt changes can be investigated from persisted responses.
- Interrupted 500-clause runs can continue without repeating completed calls.
- Provider-specific process and transport logic stays outside the application service.
- Raw provider responses may contain clause content and must never be committed automatically.


## Superseded detail

ADR 0047 supersedes the original assumption that generated proposals belong directly in the corpus annotation workspace. Generated candidates are now persisted only inside provider- and model-specific evaluation runs.
