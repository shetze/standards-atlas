# ADR 0013: Workspace, Publication, and Artifact Lifecycle

## Status
Accepted

## Goal alignment
The knowledge-engineering pipeline produces artifacts with different authority and rebuildability. Lifecycle placement must preserve the distinction between canonical documents, qualified semantic evidence, rebuildable CBox/ABox/OWL and retrieval projections, human review material, and application-specific publications.

## Context
The project produces canonical data, caches, temporary work products, human review material, generated publications, and immutable qualification evidence. Mixing these by feature makes cleanup and ownership unclear.

## Decision
Artifacts are classified primarily by **audience, authority, and lifecycle**.

- `.atlas/data/` stores persistent machine-consumable project artifacts and canonical/qualified data.
- `.atlas/work/` stores rebuildable intermediate workflow artifacts and caches.
- `local/` stores human-consumable local outputs, reviews, reports, logs, and unpublished material.
- tracked `docs/` contains project documentation; generated publication output is produced through explicit publication adapters/templates.
- Cleanup commands/scripts may remove rebuildable work but must not silently delete canonical or immutable qualification evidence.
- AtlasData/source baselines have explicit lifecycle and governance rather than being inferred from generated output.

## Consequences
Artifact ownership, cleanup, publication, and reproducibility are easier to reason about. New artifact types must declare their lifecycle instead of choosing a directory ad hoc.
