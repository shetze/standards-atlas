# ADR 0077: Extract ontology-grounded concepts and relations into rebuildable semantic artifacts

- Status: Accepted
- Date: 2026-08-25

## Context

The deterministic ABox/CBox projection introduced by ADR 0076 can only materialize facts already present in `EngineeringDocument`. Cross-domain relationship discovery needs richer engineering semantics such as activities, artifacts, roles, techniques, measures and relations between them. Those semantics often require interpretation and therefore cannot be written back as deterministic document facts.

The project already has Knowledge Domain, taxonomy and semantic-classification context that can decide whether a clause is useful for such extraction. The formal OWL ontologies define the vocabulary into which extracted knowledge must be grounded.

## Decision

Introduce a separate `DocumentSemanticExtraction` artifact for inferred engineering knowledge. It is rebuildable, auditable and remains outside the canonical `EngineeringDocument` contract.

Extraction is admitted deterministically from existing semantic context. Knowledge-kind classifications, role-semantics presence, applicability presence and process functions are routing signals; an extractor does not run blindly on every clause.

Every extracted entity must use a class declared by the selected formal ontologies. Every extracted relation must use a declared property and both endpoints must be entities from the same clause extraction. The Slice-4 extractor is not allowed to assert cross-domain equivalence or SKOS-style mappings. Those belong to later relationship discovery and assessment.

LLM-backed extraction remains behind `SemanticKnowledgeExtractor` and the existing `LlmGateway`. The concrete adapter receives the allowed formal vocabulary and uses schema-constrained output. It stores model/provider/prompt hashes and confidence as provenance, but evidence text is a non-quoted semantic rationale so protected clause text is not duplicated into the extraction artifact.

`SemanticExtractionProjectionAugmenter` may combine the rebuildable extraction artifact with the deterministic Slice-3 projection. Each inferred assertion receives its own epistemic CBox context containing confidence and extraction provenance. This augmentation does not mutate `EngineeringDocument`.

The existing formal ontology version resources may be updated destructively during the current refactoring window. Slice 4 therefore extends the current core vocabulary in place rather than introducing another compatibility version solely for additive extraction-provenance properties.

## Consequences

- inferred semantics are clearly separated from canonical document facts;
- extraction can be re-run or re-qualified independently of document migration;
- ontology vocabulary acts as a hard output boundary for LLM extraction;
- current taxonomy and Knowledge Domain work becomes deterministic extraction context rather than duplicated ontology content;
- RDF/graph stores and GraphRAG remain replaceable downstream adapters;
- cross-domain mappings are intentionally deferred to relationship discovery and assessment.
