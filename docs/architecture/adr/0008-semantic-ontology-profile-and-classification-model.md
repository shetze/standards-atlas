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

## Refactoring transition
During the current architectural refactoring, intermediate semantic ontology, profile, task, prompt, and payload versions have no backward-compatibility guarantee. Obsolete transition contracts may be removed instead of being carried as permanent migration code. In particular, removed `SemanticRole` and `responsibility_functions` representations are not readable contracts.

This exception is temporary. Before the refactoring is declared complete, the stable compatibility policy in ADR 0014 must be activated for independently consumed semantic interfaces.

## Consequences
Dimensions, profiles, and inference implementations can evolve independently. Semantic profile versions, ontology/resource versions, and task/schema versions remain explicit and are not coupled to each other. During refactoring only the intentionally retained contracts need to be supported; stable releases will follow ADR 0014's bounded compatibility policy.
