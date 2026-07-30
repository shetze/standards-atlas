# ADR-0036: Separate internal artifacts from hierarchy-based local publications

## Status

Accepted

## Date

2026-07-24

## Context

Standards Atlas previously wrote Markdown and Doorstop export artifacts below `.atlas/`. Internal processing data, copyrighted source documents and consumable results therefore shared an unclear boundary. Doorstop export and `doorstop publish` also operate on one complete document hierarchy, while future catalogs require several independent projections of the Knowledge Domain graph.

## Decision

`.atlas/` is reserved for internal, machine-readable processing and debugging artifacts. Local source material and human-consumable outputs are stored below `local/`, which is ignored by Git.

Doorstop YAML projects are generated per declared `doorstop_hierarchy` below `.atlas/doorstop/<hierarchy-key>/`. The corresponding published representation is generated below `local/exports/doorstop/<hierarchy-key>/`. Markdown exports use `local/exports/markdown/<hierarchy-key>/`.

A Doorstop hierarchy is a deterministic tree projection of the richer Knowledge Domain graph. Export and publish each operate on exactly one hierarchy. The initial `functional-safety` hierarchy contains IEC 61508 as its root and includes ISO 26262 plus the CENELEC functional-safety standards.

## Consequences

- Internal artifacts remain inspectable without being presented as deliverables.
- Copyrighted and project-specific sources have a clear non-versioned location.
- Multiple independent Doorstop hierarchies can coexist.
- Published outputs mirror their internal hierarchy key.
- Workflow execution gains a final `doorstop-publish` stage.
