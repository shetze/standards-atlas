# ADR 0061: Modular deterministic structural-taxonomy engine

## Status

Accepted

## Context

ADR 0050 introduced independent, namespaced structural taxonomy dimensions and
versioned YAML definitions below `resources/structure-taxonomies/`. The persisted
`StructuralProfile` model already supports document-family and KnowledgeDomain
categories without a central enum.

The execution side was less modular. Generic structural classification lived in
`StructuralProfileClassifier`, while ISO/IEC document-family categorization was
implemented directly in the AtlasData mapper. That coupled an input adapter to one
particular taxonomy and made adding Railway TSI, Polarion, Functional Safety, or other
deterministic classifiers require changes in unrelated code.

Structural taxonomies are intended to classify the document/text tree with classical,
deterministic algorithms. They must not depend on an LLM and must remain separate from
semantic LLM tasks.

## Decision

Introduce a deterministic structural-taxonomy engine with three explicit contracts:

1. `StructuralTaxonomyDefinition` describes the versioned category vocabulary loaded
   from `resources/structure-taxonomies/`.
2. `StructuralTaxonomyClassifier` is an interchangeable algorithm plug-in for exactly
   one taxonomy id and version.
3. `StructuralTaxonomyRegistry` resolves classifiers by `(taxonomy_id, version)`, while
   `StructuralTaxonomyEngine` composes selected classifiers with the generic structural
   profile analysis.

The engine receives taxonomy selection explicitly. It does not infer that every input
uses ISO/IEC structure or Functional Safety semantics.

The packaged YAML resources remain the category contract. The resource adapter loads
those definitions and the engine rejects categories emitted by a classifier that are
not declared by its versioned taxonomy resource.

Move the existing ISO/IEC Directives Part 2 algorithm out of the AtlasData mapper into
`IecDirectives2Classifier`. AtlasData selects that taxonomy explicitly because the
legacy AtlasData standards represented by that adapter follow the corresponding
structure. The resulting category identifiers and persisted `StructuralProfile`
representation do not change.

Keep generic cross-document analysis such as canonical section detection, annex status,
and labelled semantic-section detection in `StructuralProfileClassifier`; it no longer
accepts precomputed document/domain taxonomy categories. Taxonomy-specific categories
can only enter through the taxonomy engine.

Complex classification algorithms remain Python code. YAML describes the taxonomy
contract and configuration; Standards Atlas does not introduce a general-purpose rule
language in YAML.

## Consequences

- document-family and KnowledgeDomain classification algorithms can be added or replaced
  independently;
- input adapters no longer own taxonomy-specific classification rules;
- taxonomy ids, versions, and allowed categories are validated against packaged
  resources;
- deterministic structural analysis remains independent from semantic/LLM tasks;
- future `railway-tsi`, `polarion-export`, `functional-safety`, and `cybersecurity`
  classifiers can plug into the same engine without changing `StructuralProfile`;
- taxonomy selection must be explicit at the composition boundary;
- this slice does not implement algorithms for every taxonomy resource and intentionally
  preserves current classification behaviour.
