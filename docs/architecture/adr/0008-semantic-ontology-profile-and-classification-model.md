# ADR 0008: Semantic Ontology, Profile, and Classification Model

## Status
Accepted

## Context
Engineering semantics are multidimensional and evolve at different rates. Earlier flat `SemanticRole`/responsibility classifications coupled taxonomies, prompts, tasks, and profile versions too tightly.

## Decision
Semantic inference is modeled through three separate concepts:

1. **Semantic ontologies/vocabularies** define versioned controlled dimensions such as statement functions, knowledge kinds, process functions, applicability, and role-relation types.
2. A **SemanticProfile** composes compatible ontology dimensions for a knowledge domain and is versioned independently.
3. **Classification/extraction tasks** are versioned inference implementations that produce one or more profile dimensions.

Role semantics use grounded role relations rather than a `responsibility_functions` dimension. Role relevance/presence and relation tuple extraction are separate tasks.

Semantic classification uses canonical content plus deterministic structural context, and its inferred output remains separate from canonical document structure.

The term *semantic ontology* here means a controlled classification vocabulary. Formal OWL TBox/RBox ontologies are defined separately by ADR 0009.

## Consequences
Dimensions, profiles, and inference implementations can evolve independently. The active semantic model has no compatibility obligation to removed `SemanticRole` or responsibility-function representations.
