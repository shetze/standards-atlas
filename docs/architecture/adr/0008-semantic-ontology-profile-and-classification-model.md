# ADR 0008: Assertion-Centred Semantic Knowledge Model

## Status
Accepted

## Goal alignment
Standards Atlas extracts **explicit engineering assertions** from technical standards instead of treating clause classification as the end product. LLMs remain qualified, replaceable analysis components; they propose evidence-backed knowledge that is adopted only through explicit qualification or human review.

The canonical semantic unit is therefore an assertion about engineering entities, not a label attached to an entire clause.

## Context
The earlier multidimensional `SemanticClassification` model combined statement functions, knowledge kinds, process functions, applicability and role semantics. That model was useful for exploring the corpus, but several dimensions mix different semantic levels. In particular, `input`/`output` are usually relations between an engineering artifact and an activity, while `evidence` is a function an artifact serves for a claim rather than an intrinsic kind of artifact.

For cross-domain Functional Safety work, the important reusable knowledge is instead the set of explicit claims a standard makes about engineering entities such as specifications, plans, reports, activities, requirements, techniques and other work products.

## Decision
The intended semantic architecture has three distinct layers:

1. **Document context** contains deterministic structure, references, subject context and accepted applicability semantics. It explains how a source statement must be interpreted.
2. **Document knowledge** contains accepted `KnowledgeEntity` and `NormativeAssertion` objects embedded in the canonical `EngineeringDocument` through `DocumentKnowledge`.
3. **Formal semantic projections** map accepted document knowledge into TBox/RBox/ABox/CBox representations as rebuildable consumers.

`DocumentKnowledge` schema 1 contains:

- `EvidenceAnchor`: a text-safe reference to a canonical clause or character range; protected source text is not copied into the knowledge record;
- `KnowledgeEntity`: a normalized engineering entity with an ontology class and one or more source anchors;
- `NormativeAssertion`: an evidence-backed subject/predicate/object statement with assertion-local normative force and adoption provenance.

Normative force belongs to the individual assertion (`requirement`, `recommendation`, `permission`, `prohibition`, `informative`, or `unspecified`). A clause may therefore contribute several assertions with different functions instead of receiving one global statement-function label.

Accepted knowledge is local to its source document. Assertions reference entities and evidence anchors from the same `DocumentKnowledge` aggregate. Cross-document equivalence and transfer decisions are derived later and never alter the originating normative assertion.

Roles are ordinary engineering entities when a source statement explicitly requires them; there is no architectural requirement for a separate role-classification dimension.

Applicability remains context rather than domain knowledge. The new `ClauseApplicability` contract intentionally contains only explicit presence plus optional `included`/`excluded` polarity. Conditions, exceptions and technique usability are not folded into this core contract.

## Refactoring transition
Slice 1 introduces the target `DocumentKnowledge` and `ClauseApplicability` contracts while the existing `SemanticClassification` implementation remains temporarily operational. Slice 2 cuts context/applicability consumers over to the new boundary. Slice 3 removes the obsolete classification dimensions, resources, workflows and tests rather than preserving compatibility adapters.

No persisted `.atlas` or `local` data is migrated. The canonical EngineeringDocument persistence contract restarts at schema 1 and accepts only schema 1.

Slice 5A introduces `DocumentKnowledgeProposal` schema 1 as the non-canonical assertion proposal boundary. It mirrors the semantic shape needed for later adoption (`EvidenceAnchor`, entity proposals, assertion proposals and ontology bindings) while retaining proposal-only confidence, rationale, attempts, failures, violations and model provenance. Proposals are persisted under run-scoped `.atlas/data/knowledge-proposals/<run-id>/` paths and have no implicit conversion into `EngineeringDocument.knowledge`. The transitional `DocumentSemanticExtraction` contract remains readable only until the extractor cut-over is completed in Slice 5C.

## Consequences
Semantic qualification can operate at assertion granularity: an efficient extractor may propose several assertions from one clause and independent verification can accept some while escalating only disputed assertions. The resulting knowledge is directly usable for artifact-contract compilation, cross-domain comparison, MCP engineering workflows and evidence binding without treating classification labels as the final knowledge representation.
