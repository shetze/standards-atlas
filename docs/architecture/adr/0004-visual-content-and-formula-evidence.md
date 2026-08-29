# ADR 0004: Visual Content and Formula Evidence

## Status
Accepted

## Goal alignment
The project goal requires machine-processable knowledge without sacrificing evidential traceability. Visual material is therefore retained as source evidence even when later stages create textual, semantic, or OWL projections from it. Derived interpretations must remain linked to the visual source rather than replacing it.

## Context
Figures and formulas may carry normative meaning that is absent from surrounding text. OCR or LLM transcription can be useful but is not sufficiently reliable to replace source evidence.

## Decision
Visual content is preserved as first-class source evidence before semantic interpretation.

- Captions and layout ownership are determined structurally when possible.
- Visual formulas are preserved in their source form and linked to the containing document structure.
- Formula transcription is a separate, auditable enrichment artifact with provenance, status, and reviewability.
- Transcription never destroys or substitutes the original evidence.

## Consequences
Semantic consumers can use transcriptions while qualification and reviewers retain access to the original visual evidence.
