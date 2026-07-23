# ADR-0035: AtlasData Lifecycle and Baseline Governance

## Status

Accepted

## Context

Legacy AtlasData files are manually reviewed clause baselines. AtlasData generated from newly
onboarded Docling documents has not received the same review. Treating both classes identically
would make alignment and regression results appear more authoritative than their inputs.

## Decision

AtlasData metadata contains `lifecycle_status` with exactly three values:

- `proposed`: generated or changed baseline awaiting review;
- `reviewed`: clause structure checked by a reviewer;
- `published`: approved project baseline.

The normal transition is `proposed -> reviewed -> published`. Status changes are explicit and
forward-only through `atlasdata set-status`. Git history remains the source for authorship and
origin, so no separate origin field is introduced.

Onboarding creates `proposed` files. Regeneration may replace only an existing `proposed` file.
`reviewed` and `published` files are protected even when overwrite is requested. Existing
versioned AtlasData files are migrated to `published` without changing their clause content.

## Consequences

Workflow-generated structures are visibly provisional. Reviewed baselines cannot be silently
replaced by later extraction runs. Promotion becomes a deliberate, auditable repository change.
Older external AtlasData files without the field remain readable as `published` for compatibility,
but all AtlasData maintained in this repository carries the field explicitly.
