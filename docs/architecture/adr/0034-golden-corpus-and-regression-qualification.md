# ADR-0034: Golden Corpus and Regression Qualification

## Status

Accepted

## Context

The NormalizedDocument and EngineeringDocument contracts are deterministic, but their
continued validity cannot be established only through isolated unit tests. Changes to
Docling interpretation, layout heuristics, normalization rules or serialization may alter
several artifact layers at once. A fixed and reviewable regression basis is required.

## Decision

A versioned golden corpus is maintained under `tests/golden_corpus`. Each case contains:

- a self-contained Docling JSON input;
- a manifest with source classification and covered features;
- explicit expected invariants;
- optionally a byte-exact normalized artifact snapshot.

The corpus contains small synthetic examples, deliberately malformed extractor structures,
and reduced representative excerpts derived from real standards. Original copyrighted PDFs
are not copied into the repository; the excerpts are minimal and qualification-focused.

The `GoldenCorpusQualifier` executes extraction and normalization without updating expected
results. It produces a machine-readable report containing input and output hashes and all
failed expectations. Expected data can only be changed by an explicit repository change and
must therefore be reviewed like production code.

Two expectation styles are supported:

1. byte-exact golden artifacts for contracts whose serialization is intended to remain stable;
2. semantic invariants for cases where several equivalent representations are acceptable.

The corpus index has its own semantic version. Changes to inputs, expected artifacts,
invariants or interpretation rules require a corpus-version decision.

## Covered qualification classes

The initial corpus covers simple and multi-page clauses, repeated headers and footers,
tables and caption ownership, pictures and assets, formulas, nested lists, split headings,
hyphenation, annexes, multilingual page sequences, multipart standards, malformed Docling
structures, and a representative EN 50126-1 excerpt.

## Consequences

- cross-layer regressions become reproducible;
- expected changes are explicit and reviewable;
- qualification does not depend on private source documents or network services;
- snapshots may require intentional updates after approved schema changes;
- the corpus is evidence for regression control, not a statistical measure of all standards.
