# ADR 0044: Publish reviewed clause annotations as reproducible data

## Status

Accepted

## Context

Semantic-role qualification needs a representative corpus of clauses from licensed standards.
The standard text itself must remain local, but an annotation can be published when it refers to an
exactly identifiable clause and contains no protected clause content.

Different publishers may distribute the same standard in PDFs with different binary content and
therefore different file hashes. A PDF hash is not a suitable interoperability key. Standards Atlas
normalizes those sources into canonical `EngineeringDocument` clauses, which are expected to be
reproducible for the same standard edition.

Generated baseline proposals need human review before they become project reference data. Local
experiments must not silently override reviewed annotations committed to the repository.

## Decision

A clause annotation is identified by knowledge domain, document key, and clause identifier. It also
contains a SHA-256 `content_hash` over the normalized clause content only. The hash is an
integrity and staleness check, not the clause identity and not a hash of the source PDF.

Corpus manifests and annotations are content-safe YAML documents. They contain references,
classification values, provenance, review evidence, and hashes, but no clause text.

Generated proposals are stored below `local/evaluation/corpora`. After explicit human review they
may be published below `data/evaluation/corpora` and committed to Git. Publication changes the
lifecycle from `reviewed` to `published` while preserving the original proposal and review evidence.

Annotation resolution uses this precedence:

1. published annotation below `data`;
2. reviewed local annotation;
3. local proposal.

When published and local variants coexist, the published annotation is selected and the local file
is reported as shadowed. A clause-hash mismatch is treated as a stale annotation and is rejected.

The canonical annotation retains both the generated proposal and the reviewed classification. A
review can accept, correct, reject, or mark the proposal as ambiguous. This separation allows later
measurement of baseline-proposal quality against the reviewed corpus.

## Consequences

### Positive

- Reviewed annotations can be shared without publishing licensed standard text.
- Users with the same standard edition can reconstruct clauses locally and verify corpus integrity.
- Different publisher PDFs do not invalidate otherwise identical normalized clauses.
- Published reference data deterministically override local experiments.
- Proposal quality remains measurable because review does not overwrite model output.
- Changed normalized clauses make affected annotations fail explicitly as stale.

### Negative

- Reproducibility depends on stable normalization behavior and clause identifiers.
- A normalization change may require review or migration of clause hashes.
- Human-friendly review exports still need a separate implementation because canonical YAML omits
  clause text.

## Alternatives considered

### Use hashes of source PDF files

Rejected because equivalent standards from different publishers can have different PDF hashes.

### Use the clause hash as the only identity

Rejected because identical text can occur in multiple clauses and standards. Domain, document, and
clause references preserve context while the hash verifies content.

### Keep all annotations below `local`

Rejected because reviewed annotations are reusable qualification evidence and should be versioned
with the project.

### Let local annotations override published annotations

Rejected because an unreviewed local generation could silently change benchmark ground truth.
