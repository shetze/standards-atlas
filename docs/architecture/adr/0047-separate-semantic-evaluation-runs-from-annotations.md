# ADR 0047: Separate semantic evaluation runs from reviewed annotations

## Status

Accepted

## Context

A semantic corpus clause may be evaluated repeatedly with different providers,
models, prompts, task versions, and generation parameters. Treating the first
model proposal as the clause annotation causes later runs to be skipped and
loses the experiment matrix required for model comparison and qualification.

## Decision

Generated model output is persisted as an immutable candidate inside a
provider- and model-specific evaluation run. It is not written directly into
the corpus annotation workspace.

Run identity contains the corpus, prompt, provider, and model:

```text
local/evaluation/runs/<corpus>/<prompt>/<provider>/<model>/<clause>/
    request.json
    response.json
    evaluation.yaml
```

`evaluation.yaml` contains run identity, complete provenance, and the generated
annotation candidate. Resume and `--limit` operate only within that exact run.
A Granite candidate therefore never causes a Codex candidate to be skipped.

The annotation workspace remains a separate lifecycle for human decisions:

```text
candidate evaluations -> HITL decision -> reviewed annotation -> published gold
```

Candidate aggregation and review are separate application services and must not
change or overwrite evaluation evidence.

## Consequences

- Multiple providers and models can evaluate the same clause independently.
- Prompt and model benchmarks remain reproducible.
- Generated evidence is never silently replaced.
- The HITL workflow can compare all candidates before creating gold data.
- Existing shared proposal files are no longer used as resume markers.
