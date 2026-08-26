# ADR 0045: Build representative semantic-evaluation corpora by stratified coverage

## Status

Accepted

## Context

Balancing a sample only by document prevents large standards from dominating, but it does not
ensure coverage of the clause characteristics that influence semantic-role classification. The
qualification corpus must be reproducible, content-safe when published, and transparent about the
population from which its clauses were selected.

The normalized clause text remains local. Other users who possess the same standards must be able
to reconstruct the selected clauses and verify their normalized clause hashes.

## Decision

Standards Atlas provides a `representative_stratified` corpus-selection strategy. It evaluates the
complete filtered clause population and records these dimensions for each candidate:

- document key;
- clause type;
- structurally known semantic role set;
- hierarchy depth derived from the normalized clause reference;
- normalized text-length class;
- presence or absence of a title.

Selection is deterministic for a fixed population and seed. A greedy coverage algorithm favours
uncovered and rare stratum values until the requested corpus size is reached. The algorithm is not
intended to reproduce the population distribution exactly; it deliberately improves coverage of
minority and difficult cases for model qualification.

The local corpus consists of two artefacts:

- `dataset.json`, which may contain protected clause text for local annotation and benchmarking;
- `corpus.yaml`, which never contains clause text and can be reviewed and published.

The manifest contains the stable clause reference, normalized `content_hash`, assigned strata,
filters, seed, strategy, complete population counts, and selected counts. The selected clause order
is part of the reproducible corpus definition.

## Consequences

### Positive

- Minority clause types and semantic roles are less likely to disappear from the corpus.
- The selection can be reproduced and audited from its seed, filters, strata, and population.
- Published manifests remain safe for Git because they contain no licensed clause text.
- Population and sample statistics make corpus bias visible before model benchmarking.
- The design supports the target corpus of 500 clauses without hard-coding that size.

### Negative

- The sample is optimized for qualification coverage, not for estimating raw production prevalence.
- Changes to normalization, clause references, or the stratum definitions may produce a new corpus.
- Hierarchy depth currently depends on the normalized reference syntax and may require refinement for
  unusual standards.

## Alternatives considered

### Continue balancing only by document

Rejected because it provides no explicit coverage of roles, clause types, hierarchy, or difficult
text classes.

### Sample in proportion to the population

Rejected as the sole qualification corpus because rare roles would receive too few examples for
meaningful per-class metrics.

### Persist the clause text in the published manifest

Rejected because standard text is protected and can be reconstructed locally by authorized users.


## Amendment: content eligibility and context separation

Corpus sampling excludes clause occurrences whose normalized plain-text content is empty or
whitespace-only. A title does not make a clause eligible because headings belong to structural
context, not clause content. The `content_hash` is calculated exclusively from normalized clause
content. Titles, references, hierarchy, document identity, and structural roles are persisted as
separate context. The manifest records total and eligible occurrences, empty exclusions, unique
contents, and duplicate content groups so content-only and context-aware evaluations can use the
same reproducible corpus without conflating the two identity levels.


## Multipart family views

Current workflows build corpora exclusively from canonical physical EngineeringDocuments; composed family views live below `.atlas/work` and are not enumerated by the corpus provider. Exact-occurrence collapsing remains as a legacy safeguard for older workspaces that still contain persisted family-document copies. This does not collapse genuinely repeated content with different clause identifiers.
