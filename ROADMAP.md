# Roadmap

This document provides a high-level view of the long-term evolution of
standards-atlas. Detailed implementation plans are maintained under
`docs/roadmap/`.

## Near term

### Qualify structured table knowledge

T1-T3 now provide first-class table structure, deterministic normalization, and structured
knowledge mapping, and T4 adds retrieval-specific table/row/concept/relation projections behind
replaceable tokenizer and index ports. Slice 6A projects supported portable engineering matrices
into the same assertion-centred `DocumentKnowledgeProposal` contract as prose. Slice 6B unifies
prose and table proposal runs with deterministic document-local entity resolution. Slice 6C now
projects qualified IEC 61508 technique recommendations through reified recommendation entities
without losing SIL, recommendation level, alternative-group, or reference semantics. Next,
introduce typed assertion/table corpora and dedicated qualification without weakening the proposal,
qualification, and adoption boundary. Slice 7A adds versioned development/holdout assertion
golden suites plus deterministic entity/assertion, normative-force, and grounding metrics. Slice 7B
now adds threshold-free Efficient → Verify → Escalate execution with exhaustive independent missing
assertion detection and targeted clause escalation. Next, introduce explicit holdout and
automatic-adoption policy in Slice 7C.

### Qualify existing standards

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


## Status after 0.8.6

The architectural refactoring planned for the 0.8.x series is complete. Version 0.8.6 additionally establishes the Gemara/ComplyTime governance integration: linked Guidance and Control catalogs, use-case selection profiles, candidate analysis, Gemara Policy scaffolding, ComplyPack authoring hand-off, and EvaluationLog feedback with source-clause provenance. Near-term work can therefore focus on qualification quality, taxonomy coverage, and engineering functionality rather than structural reorganization.
