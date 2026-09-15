# Structural classification

Standards Atlas separates deterministic document structure from engineering meaning.

## Structural profile

`StructuralProfile` is attached to each clause and records independent structural dimensions. Current dimensions include canonical document section, document/domain categories, semantic sections used for structural routing, and annex status. The dimensions are derived from headings, hierarchy, document metadata, annex declarations, and explicitly selected structure taxonomies.

The structural model does not contain statement-function, knowledge-kind, process-function, applicability-function, or role-classification fields. Those retired clause-classification dimensions are not compatibility aliases.

## Structure to context and knowledge

The deterministic taxonomy stage enriches the canonical `EngineeringDocument` with `StructuralProfile`, `StructuralContext`, reference edges, and structural scope reach. `document enrich-context` then materializes routing and deterministic subject context. Accepted applicability is an independent qualified enrichment.

These values form the CBox used by later engineering-knowledge extraction. Formal extraction proposes source-bound `KnowledgeEntity` and `NormativeAssertion` objects against the selected ontology vocabulary. It does not recreate a multidimensional clause classification.

The stage boundary is deliberate: structural taxonomy answers where a clause belongs and how document structure reaches other clauses; evidence-backed assertions represent what the source actually states about engineering entities and relations.

## Taxonomy resources and deterministic engine

Versioned structure taxonomies live below `resources/structure-taxonomies/`, separated into document-level and domain-level definitions. Functional-safety taxonomies may specialize general ISO/IEC document structure without being imposed on railway TSI, Polarion, cybersecurity, or other knowledge domains.

The YAML file is the versioned category contract; classification behaviour is supplied by a `StructuralTaxonomyClassifier` implementation. `StructuralTaxonomyRegistry` resolves those implementations by taxonomy id and version, and `StructuralTaxonomyEngine` composes explicitly selected document/domain classifiers with the generic `StructuralProfileClassifier`. Emitted categories are checked against the corresponding YAML definition.

This layer is deterministic and LLM-free. Complex tree algorithms remain normal Python code rather than being encoded in a general-purpose YAML rule language. Applicability qualification and formal assertion extraction are separate concerns.

## Inheritance

Defaults and inheritance are explicit structural rules. Core normative sections may inherit normative status; annex declarations determine annex status; notes, examples, and guidance remain informative where the governing standard requires that distinction. Whole informative parts can define a document-level default.

## Evaluation

Structural classification is tested deterministically. Probabilistic qualification is reserved for semantic tasks that cannot be derived reliably from structure alone, notably applicability and formal assertion extraction. Human review remains the authority for unresolved or disputed engineering meaning.
