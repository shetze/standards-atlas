# ADR 0060: Classify workspace artifacts by audience and lifecycle

## Status

Accepted

## Context

Standards Atlas historically wrote generated artifacts directly below `.atlas/`
and `local/`. Those locations mixed several different lifecycle requirements:
canonical machine state, disposable caches, workflow scratch data, published
human-readable documents, and HITL review material.

That made cleanup unsafe and made it difficult to tell whether an artifact was
part of the machine state or intended for direct human use.

## Decision

Generated artifacts are classified by audience and lifecycle.

```text
.atlas/
├── data/   # persistent machine-facing state
├── cache/  # disposable reproducible caches
└── work/   # scratch state retained from the latest workflow run

local/
├── exports/ # persistent human-facing publications
├── review/  # all HITL and editable review artifacts
└── evaluation/ # human-facing reports and immutable evidence archives
```

The following invariants apply:

1. `.atlas/data` contains persistent machine-readable state. Removing it can
   discard project state or require expensive regeneration.
2. `.atlas/cache` contains only artifacts that may be deleted at any time
   without changing the result of a complete rerun.
3. `.atlas/work` contains temporary workflow state. It is retained after a run
   for debugging and removed automatically before the next workflow run.
4. `local` is the human boundary. Artifacts stored there are intended to be
   read, edited, reviewed, published, archived, or otherwise consumed by a
   human.
5. All HITL artifacts are stored below `local/review`.
6. `standards-atlas clean` never removes `local` artifacts.

The CLI default engineering-document workspace is `.atlas/data`. Qualification
corpora, raw proposal runs, and machine qualification state also move below
`.atlas/data/evaluation`. Human-facing qualification review queues remain below
`local/review/qualification`; human-facing reports and immutable archives may
remain below `local/evaluation`.

LLM state follows the same model: runtime state is stored below
`.atlas/work/llm`, while response caches are stored below `.atlas/cache/llm`.

## Cleanup lifecycle

`standards-atlas clean` removes `.atlas/work` by default. `--cache` additionally
removes `.atlas/cache`. Persistent `.atlas/data` is removed only with the
explicit destructive combination `--data --force`.

`workflow run` removes `.atlas/work` before executing the new plan. Scratch
artifacts from the completed or failed run are then retained for debugging
until the next workflow execution or an explicit clean.

## Consequences

Storage intent is visible from the path alone. Workflow cleanup becomes safe
and deterministic, and HITL integrations have one stable root. Existing
workspaces must be migrated once; the repository provides a migration script
for tracked legacy artifacts and documents the corresponding moves for local
runtime state.
