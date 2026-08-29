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
