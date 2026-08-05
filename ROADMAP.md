# Roadmap

This document provides a high-level view of the long-term evolution of
standards-atlas. Detailed implementation plans are maintained under
`docs/roadmap/`.

## Near term

### Qualify structured table knowledge

Introduce typed table corpora and dedicated qualification for schema recognition, record
extraction, relationships, references, and recommendation matrices without weakening the
existing clause-classification boundary.

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


## Status after 0.8.1

The architectural refactoring planned for the 0.8.x series has been completed. Future work can focus on functionality rather than structural reorganization.
