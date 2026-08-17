# ADR 0056: Enrich visual formulas through auditable transcription artifacts

## Status

Accepted.

## Context

ADR 0055 preserves formulas that Docling identifies but cannot transcribe by attaching a source-derived PNG to the canonical `FormulaBlock`. The next stage must let an external multimodal agent transcribe those images without making LLM execution part of deterministic PDF normalization or losing the distinction between source evidence and model-derived semantics.

Directly mutating EngineeringDocuments from an MCP client would make provenance weak and retries difficult to audit. Generating MathML as the first representation would also add avoidable structural generation complexity.

## Decision

Formula transcription is a separate enrichment stage. Standards Atlas exposes visual-only formulas through MCP and accepts LaTeX as the canonical surface transcription format for this stage.

Each accepted transcription is first persisted as a versioned `FormulaTranscriptionArtifact` below `.atlas/enrichments/formula-transcriptions/`. The artifact records the stable formula identifier, document/clause/block identity, source image hash, LaTeX expression, optional confidence, and actor/provider/model provenance. The application then deterministically applies that artifact to the corresponding `FormulaBlock`, changing its status from `visual_only` to `machine_transcribed` while retaining the original PNG and source evidence.

MCP exposes three operations:

- `list_untranscribed_formulas`
- `get_formula`
- `submit_formula_transcription`

The mutating operation is disabled by default and requires the explicit `capabilities.formula_transcription` configuration flag. Existing document allowlists continue to apply.

## Consequences

Normalization remains deterministic and independent of LLM availability. Formula images remain the recoverable source representation even after transcription. Machine-derived semantics have explicit provenance and can be reprocessed or reviewed later. LaTeX becomes the surface-transcription interchange format; semantic AST, Content MathML, or OpenMath interpretation remains a later concern.
