# ADR 0007: Structural Taxonomy and Context Model

## Status
Accepted

## Goal alignment
Deterministic taxonomy is the first semantic-context stage of the knowledge-engineering pipeline. It captures reproducible document and interpretation context without claiming domain knowledge. Together with accepted abstract semantic functions, this context contributes to the CBox used by later knowledge extraction; domain assertions themselves belong to the ABox defined by ADR 0009.

## Context
Document structure determines the context in which semantic statements are interpreted. A single flat semantic-role field cannot represent headings, scopes, structural roles, and inherited context.

## Decision
Structural interpretation is deterministic, multidimensional, and separate from semantic inference.

- Versioned **structural taxonomies** define independent dimensions such as structural role and applicability/scope context.
- A modular taxonomy engine classifies document structure using deterministic rules and evidence.
- Structural nodes and leaves are distinct; headings provide context, and short node content may act as structural summary evidence.
- Structural scope reach is materialized deterministically and cascade resolution preserves provenance.
- Sequence and reference relations are structural evidence and may be used by later semantic stages.
- Structural classification never assigns inferred engineering meaning that requires an LLM.

## Consequences
Semantic classifiers receive explicit structural context without owning or recreating structural logic. Structural results are reproducible and independently testable.

### Source-grounded informational routing safeguard (2026-09-09)

A well-formed address is not evidence of a governing relation. A bounded application policy,
`source-grounded-information-v1`, may reclassify generated reading-list/FAQ scopes only when the
quotations are verified in a non-governing source passage. It reconstructs explicit informational
references from that passage, rather than treating alleged scope reaches as trusted source data.
Unrelated interpretation paragraphs are not conditions on earlier reading lists. Mixed or
unverified material cannot justify deletion; uncertain mixed candidates require review/correction.
This is a limited English navigation policy, not a replacement for semantic interpretation.

The same policy is used before v3 scope address construction and in model-free canonical repair.
Its revision, extractor revision and prompt content participate in generation identity. Repair
retains original source/provenance and records full before/after diagnostics privately; protected
attributes remain authoritative. Public projections still carry no literal evidence or WIP audit.
Qualified citations separate standard identity from coordinate lists/ranges. Shared coordinates
produce separate targets but retain the full original text span; target identity remains exact,
physical-document- and edition-aware, and unresolvable groups are never partly fabricated.
