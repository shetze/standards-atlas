# ADR 0002: Canonical Document and Provenance Model

## Status
Accepted

## Context
Extraction and publication formats are unsuitable as the long-lived engineering representation. The project needs one canonical document model that preserves the complete auditable knowledge state of a physical source document while keeping source-derived facts, deterministic interpretation, model-assisted enrichment, and community-curated authority distinguishable.

Deterministic processing is not equivalent to certainty. Source extraction, structural classification, scope detection, and reference resolution can all be imperfect even when their algorithms are reproducible. AtlasData provides a community-curated authoritative overlay that can confirm or correct these generated properties over time.

## Decision
`EngineeringDocument` is the canonical representation of one **physical source document or standard part** and contains its complete accepted engineering knowledge state.

Knowledge-bearing clause data is explicitly separated into:

- `ClauseBaseline`: source-derived and deterministic/classical facts such as structured content, headings, hierarchy, structural profile/context, scope/reference evidence, resolved reference relations, and publication attributes;
- `ClauseEnrichments`: interpretative and model-assisted derived knowledge such as semantic classification, applicability, role relations, and other semantic/ontological enrichment;
- `KnowledgeStateProvenance`: attribute-level provenance for facts that are still generated rather than authoritatively confirmed.

`baseline` means that a property belongs to the source/structural interpretation of the document. It does **not** mean that the property is infallible or community-confirmed.

Generated attributes are addressed by stable paths such as `baseline.structural_context` or `enrichments.semantic.statement_functions` and record the generator and generation method. A generated marker means "not yet confirmed by an authoritative source", not "unreliable".

AtlasData is the primary community-curated authoritative source for document structure, tags, and accepted semantic confirmations. Values imported from authoritative AtlasData do not require a generated marker. When processing creates or replaces an unconfirmed property, that property is marked generated until AtlasData or another explicitly authoritative source confirms it.

Canonical construction follows these rules:

- normalized/extracted evidence is losslessly attributable to source locations;
- clause content is constructed from aligned, bounded content ranges rather than unconstrained text inference;
- page starts, terms, headings, list structure, tables, figures, formulas, references, and structural context retain source anchors when available;
- deterministic transformations record lineage/configuration identity and mark newly generated attributes;
- deterministic reference relations belong to the baseline, not to semantic classification;
- accepted semantic and ontological enrichments remain inside the `EngineeringDocument`, but under the enrichment boundary with generation provenance;
- model-run candidates, qualification evidence, disagreements, and rejected proposals remain evaluation/run artifacts until accepted into the canonical knowledge state.

A standard family is **not** represented by a synthetic canonical `EngineeringDocument`; family composition is a derived publication view defined by ADR 0006.

## Consequences
The canonical document contains everything needed to inspect the accepted knowledge state without conflating origin, authority, and inference method. Community-maintained AtlasData can progressively replace generated assertions with authoritative knowledge without requiring every extraction or inference algorithm to reach perfect accuracy.

The schema is more explicit and carries additional provenance metadata. This is intentional: auditability and progressive community curation take precedence over a flatter serialized representation.
