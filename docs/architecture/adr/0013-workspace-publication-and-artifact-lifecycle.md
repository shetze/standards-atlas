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

## Knowledge persistence and protected evidence

The public AtlasData enrichment companion transports selected attribute values and explicit
origin, not complete private documents. `.atlas/data/knowledge-evidence/<sha256>.json` contains
immutable source-bearing context and raw provenance needed for lossless private hydration.
These blobs are persistent evidence, not a cache: cleanup of work/cache must not remove them.
They are protected by content hashes and private file permissions and must not be committed into
the public AtlasData tree. The export adapter rejects an evidence store inside that tree.

Export/import commands stage and validate all selected documents before any persistence write.
Each file replacement is atomic and unchanged outputs are byte-stable. This is not a transaction
across multiple files or a concurrent-writer lock. Validation failures precede writes, while an
operating-system error during commit may leave a partially completed batch that must be rerun.
Explicit local change reports describe values/statuses without disclosing protected context text.

## Consequences
Artifact ownership, cleanup, publication, and reproducibility are easier to reason about. New artifact types must declare their lifecycle instead of choosing a directory ad hoc.
