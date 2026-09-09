# ADR 0002: Canonical Document and Provenance Model

## Status
Accepted

## Goal alignment
The `EngineeringDocument` is the **canonical document-centered representation**, not the knowledge base itself. It preserves source evidence, deterministic context, and accepted clause-level semantic enrichments needed to reproduce and audit downstream knowledge projections. Cross-document knowledge integration belongs to the formal semantic/knowledge layer defined by ADR 0009.

This separation prevents OWL, GraphRAG, Doorstop, or any other consumer-specific representation from becoming a second document source of truth.

## Context
Extraction and publication formats are unsuitable as the long-lived engineering representation. The project needs one canonical document model that preserves the complete auditable document-centered state of a physical source document while keeping source-derived facts, deterministic interpretation, accepted semantic context, model-assisted enrichment, and community-curated authority distinguishable. Cross-document formal knowledge is a derived layer rather than part of canonical document identity.

Deterministic processing is not equivalent to certainty. Source extraction, structural classification, scope detection, and reference resolution can all be imperfect even when their algorithms are reproducible. AtlasData provides a community-curated authoritative overlay that can confirm or correct these generated properties over time.

## Decision
`EngineeringDocument` is the canonical representation of one **physical source document or standard part** and contains the accepted document-centered evidence and enrichments required to reproduce and audit downstream knowledge projections.

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
- accepted clause-level semantic/context enrichments may remain inside the `EngineeringDocument` under the enrichment boundary with generation provenance; formal OWL ABox assertions and cross-document graph integration remain derived knowledge projections;
- model-run candidates, qualification evidence, disagreements, and rejected proposals remain evaluation/run artifacts until accepted into the canonical knowledge state.

A standard family is **not** represented by a synthetic canonical `EngineeringDocument`; family composition is a derived publication view defined by ADR 0006.

## Attribute acceptance and confirmation (schema 9)

Qualification remains read-only. `KnowledgeAdoptionService` may explicitly accept selected
final results as generated enrichment; this is not community confirmation. The same typed
attribute merge is used by semantic and context enrichment writers. Confirmed values and
coupled groups are protected; unrelated accepted attributes can still change. Omitted
fields never clear existing values. Negative presence clears incompatible generated details.

`KnowledgeStateProvenance` now records explicit confirmations in addition to generated
attributes. Absence of a generated marker alone is not proof of authority: a default may
never have been evaluated. Generated assessments distinguish `known` and `unknown`;
no assessment is `not_evaluated`. Vote support describes the identified decision inputs,
not a measured probability of correctness. Explicit primary labels are separate from sets.

Canonical writers emit schema 9. Schema 8 remains readable within the bounded compatibility
window, with a deprecation warning. Populated unmarked v8 enrichments are retained as
protected `unattributed_attributes`, not silently labeled generated or authoritative.
An explicit confirmation resolves that uncertainty. Loading does not rewrite the source.

This does not introduce a public enrichment sidecar or promote generated classifications
into curated AtlasData tags. The existing public-annotation path remains a separate,
explicitly reviewed publication boundary; its `--merge` option preserves unaddressed tags.

## Consequences
The canonical document contains everything needed to inspect its accepted document-centered state and to reproduce downstream semantic projections without conflating origin, authority, and inference method. Community-maintained AtlasData can progressively replace generated assertions with authoritative knowledge without requiring every extraction or inference algorithm to reach perfect accuracy.

The schema is more explicit and carries additional provenance metadata. This is intentional: auditability and progressive community curation take precedence over a flatter serialized representation.
