# ADR 0065: Separate structural taxonomy from semantic ontology

## Status

Accepted

## Context

Standards Atlas already has a deterministic structural-taxonomy engine and independently
versioned semantic label spaces. The latter were still named semantic taxonomies and were
owned by the semantic-qualification package. That naming and package ownership obscured
the intended architecture: document structure is classified deterministically first,
while semantic meaning is interpreted later with qualified classifiers that may use LLMs.

The semantic dimensions currently include statement functions, knowledge kinds, process
functions, applicability functions, and responsibility functions. They evolve
independently and can be composed differently for a Knowledge Domain or semantic task.

## Decision

Introduce `application.ontology` as an application boundary independent from evaluation
and qualification. It owns these contracts:

- `OntologyDefinition` for one independently versioned semantic dimension;
- `OntologyReference` and `OntologyProfile` for modular composition;
- `OntologyDefinitionRepository` as the resource-loading port;
- `OntologyClassifier`, `OntologyRegistry`, and `OntologyEngine` as the future production
  classification boundary;
- `OntologyContext` as the input contract that later slices will enrich with taxonomically
  derived structural context.

Store ontology resources under
`resources/ontologies/<ontology>/<version>/ontology.yaml`. Semantic tasks reference these
resources through an `ontologies` mapping. Qualification remains a consumer of ontology
contracts rather than their owner.

Structural taxonomy and semantic ontology are different architectural concepts:

- taxonomy derives structural context from document structure with deterministic,
  classical algorithms and does not depend on an LLM;
- ontology classifies semantic meaning and may use qualified LLM classifiers;
- ontology may consume the structural context produced by taxonomy;
- neither layer owns the other's classification logic.

This slice establishes contracts and resource ownership only. It intentionally does not
add a workflow ontology stage and does not change classification results. Later slices
will harden references, materialize structural context, and add the production ontology
stage.

## Consequences

- semantic ontology vocabulary is no longer owned by `semantic_qualification`;
- ontology dimensions can be composed independently for tasks and future Knowledge
  Domains;
- qualification and production classification can share ontology contracts without
  sharing use-case ownership;
- packaged ontology resources have their own schema family and path;
- existing semantic values and task output schemas remain unchanged;
- the architecture now has an explicit boundary on which the later taxonomy-to-ontology
  workflow can be built.

## Related decisions

- ADR 0051: Multidimensional semantic classification
- ADR 0054: Model engineering knowledge as an orthogonal ontology
- ADR 0061: Modular deterministic structural-taxonomy engine
- ADR 0062: Separate semantic taxonomies from semantic tasks (superseded)
