# Persistence and lineage

![Artifact lineage](diagrams/svg/artifact-lineage.svg)

Every derived artefact should answer four questions: which source produced it, which options and tool version were used, which prior artefact it depends on, and which human decision changed it.

The filesystem repositories under `.atlas/` persist stage-specific contracts. Transformation ledgers record deterministic operations. Reviewed alignments retain both the machine proposal and manual override. Engineering documents retain source evidence without embedding private adapter objects.

Invalidation follows dependencies. A changed page selection invalidates extraction-derived normalization and alignment. A changed AtlasData baseline invalidates alignment but does not require reconverting an unchanged PDF. Export changes normally invalidate only target projections.
