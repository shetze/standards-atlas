# ADR-0033: EngineeringDocument Construction Contract

## Status

Accepted

## Context

The NormalizedDocument contract, transformation ledger and artifact lineage protect the
pipeline up to normalized content. Construction of the canonical EngineeringDocument
still combined reviewed alignment ranges and normalized items without one closed,
persisted proof that all active content had been accounted for exactly once.

The construction boundary must reject stale or altered alignment artifacts and must make
front matter, back matter, inter-clause content, structural headings and following-label
items explicit. Every generated ContentBlock must remain traceable to active
NormalizedItems and their SourceEvidence.

## Decision

Introduce a deterministic `EngineeringConstructionContract` that is evaluated before an
EngineeringDocument is persisted. A valid contract requires:

- at most one alignment entry per Clause;
- complete and non-inverted ranges;
- no overlap between Clause ranges;
- every active NormalizedItem assigned exactly once or covered by an explicit
  `front_matter`, `between_clauses` or `back_matter` range;
- every `following_label_item_id` to identify an active item inside its Clause range;
- structural heading items and following-label items to be counted separately while
  remaining part of the assigned range;
- the alignment's normalized-document hash to equal the current normalized artifact;
- a reviewed alignment to retain a valid integrity manifest and to refer to the current
  automatic alignment inputs;
- every generated ContentBlock to reference at least one active NormalizedItem and carry
  SourceEvidence.

The contract contains stable hashes of the normalized document, selected alignment and
automatic alignment, deterministic diagnostics and a complete coverage summary. It is
persisted as `.atlas/construction/<document-key>/contract.json`.

Applying review overrides writes `reviewed.integrity.json`, containing the reviewed
alignment hash and the automatic alignment hash on which it was based. Construction
fails if either value no longer matches.

The EngineeringDocument lineage directly references the selected alignment and the
construction contract in addition to the normalized artifact.

## Consequences

EngineeringDocument construction now fails closed instead of silently losing,
duplicating or misassigning normalized content. Front matter and similar regions remain
available as explicit alignment evidence but are not converted into Clause content.

Previously created reviewed alignments without an integrity manifest must be regenerated
or have their overrides reapplied before they can be used for construction.

ContentBlock schema remains backwards compatible because `normalized_item_ids` defaults
to an empty tuple for older persisted documents. Newly constructed content is required
to populate it.

## Alternatives considered

### Rely on alignment statistics

Rejected because aggregate counts cannot prove item-level partitioning, freshness or
ContentBlock provenance.

### Infer gaps during construction

Rejected because silently assigning front matter or inter-clause content would make the
canonical document dependent on undocumented heuristics.

### Trust reviewed.json as immutable

Rejected because a private workspace file can be edited after review. A separate,
content-addressed integrity manifest is required.
