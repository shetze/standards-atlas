# ADR 0002: Canonical Document and Provenance Model

## Status
Accepted

## Goal alignment
`EngineeringDocument` is the canonical document-centred representation. It preserves source content, deterministic context, accepted contextual enrichments and accepted engineering knowledge required to reproduce downstream projections. Cross-document integration, retrieval indexes and OWL graphs remain rebuildable consumers.

## Context
Extraction and publication formats are unsuitable as long-lived engineering representations. Standards Atlas needs one canonical model that keeps source-derived facts, deterministic interpretation, accepted model-assisted results and their provenance distinguishable without turning a retrieval or graph format into a second source of truth.

The current refactoring does not require compatibility with persisted `.atlas` or `local` data. Those workspaces are regenerated from source, so obsolete intermediate schemas and migration code would only increase complexity.

## Decision
`EngineeringDocument` represents one physical source document or standard part and owns four relevant knowledge boundaries:

- `ClauseBaseline`: source-derived and deterministic/classical facts such as structured content, hierarchy, structural profile/context, reference evidence and publication attributes;
- `ClauseEnrichments`: accepted clause-level interpretation context containing applicability, context routing and subject context only; the former clause-classification block was removed by the Slice 3 clean break;
- `DocumentKnowledge`: accepted assertion-centred engineering knowledge consisting of `EvidenceAnchor`, `KnowledgeEntity` and `NormativeAssertion` objects;
- `KnowledgeStateProvenance`: attribute-level provenance for generated clause context that is not yet authoritatively confirmed.

`baseline` describes ownership and processing, not certainty. Deterministic outputs may still carry generated provenance until reviewed or replaced by an authoritative source.

`DocumentKnowledge` follows stricter rules:

- only accepted knowledge belongs in the canonical aggregate;
- model proposals, disagreements and rejected candidates remain external evaluation artifacts;
- every entity is grounded in one or more `EvidenceAnchor`s;
- semantic classes and predicates are absolute IRIs bound to explicit formal ontology versions;
- every assertion has a source clause, subject, predicate, object, assertion-local normative force, evidence anchors and adoption provenance;
- evidence anchors reference a canonical clause surface (`body` or `heading`) by source-clause identity and optional character range and may bind a SHA-256 hash without copying protected text;
- document validation rejects unknown clauses, invalid ranges and supplied hashes that do not match canonical content;
- formal projection rejects classes or predicates not declared by the ontology versions recorded in the canonical knowledge aggregate;
- cross-document equivalence and transfer decisions are derived later and never rewrite source assertions.

A standard family is not represented by a synthetic canonical `EngineeringDocument`; family composition remains a derived view.

## Clean-break persistence contract
The EngineeringDocument persistence envelope restarts at **schema 1**. During the current refactoring:

- writers emit schema 1 only;
- readers accept schema 1 only;
- there is no reader, upgrader or migration path for previous EngineeringDocument schemas;
- `.atlas` and `local` are deleted before rebuilding and testing the new state;
- schema 1 remains the current marker until a deliberate future compatibility policy is adopted.

`DocumentKnowledge` is embedded in EngineeringDocument and likewise starts at schema 1. Its marker documents the internal contract but does not create a second independently persisted canonical artifact.

## Acceptance and provenance
Qualification is not canonical adoption by itself. A model-assisted result becomes canonical knowledge only when an explicit adoption path records suitable `KnowledgeProvenance`; future slices may use qualified automatic acceptance, human review, deterministic derivation or controlled import as distinct methods.

Generated clause-context attributes remain protected by the existing `KnowledgeStateProvenance` rules until Slice 2/3 simplify that boundary. This slice deliberately does not reinterpret existing classification results as `DocumentKnowledge`.

## Consequences
Standards Atlas has a canonical place for engineering-domain assertions without conflating them with clause classification or formal graph projections. The clean schema reset eliminates compatibility code for disposable refactoring workspaces. Later slices can replace the old semantic classifier incrementally while keeping deterministic document processing operational.
