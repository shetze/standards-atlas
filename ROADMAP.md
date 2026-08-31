# Roadmap

This document provides a high-level view of the long-term evolution of
standards-atlas. Detailed implementation plans are maintained under
`docs/roadmap/`.

## Near term

### Qualify structured table knowledge

T1-T3 now provide first-class table structure, deterministic normalization, and structured
knowledge mapping, and T4 now adds retrieval-specific table/row/concept/relation projections
behind replaceable tokenizer and index ports. Introduce typed table corpora and dedicated
qualification for schema recognition, record mapping, relationships, references, recommendation
matrices, and retrieval quality without weakening the existing clause-classification boundary.

### Classify existing standards

Apply the established taxonomy and Structural Profiles to the existing
standards corpus and continuously improve quality through evaluation.

## Medium term

### Extend the taxonomy to further standards domains

Generalise the Functional Safety taxonomy to additional standards domains while
preserving a common canonical model.

### Extend the taxonomy to further document classes

Support additional engineering artefacts such as Technical Specifications for
Interoperability (TSI), Polarion exports and similar document classes.

## Long term

### Complete the IntelliDoc refactoring

Re-establish the original IntelliDoc capabilities on top of the new
architecture, including RAG-assisted and LLM-based relationship mapping across
Knowledge Domains.

### Expand MCP capabilities

Expose Knowledge Domains through progressively richer MCP skills for search,
analysis, navigation, relationship exploration and engineering workflows.

See `docs/roadmap/` for detailed implementation plans.


## Status after 0.8.5

The architectural refactoring planned for the 0.8.x series is complete. Version 0.8.5 also establishes typed workflow manifests, immutable qualification evidence, improved multidimensional cascade semantics, formula preservation/transcription, and optional LLM-assisted normalization-quality qualification. Near-term work can therefore focus on qualification quality, taxonomy coverage, and engineering functionality rather than structural reorganization.
