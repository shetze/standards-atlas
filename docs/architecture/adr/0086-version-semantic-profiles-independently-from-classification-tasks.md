# ADR 0086: Version semantic profiles independently from classification tasks

## Status

Accepted

## Context

The semantic classification pipeline historically used a task reference such as
`semantic-profile-classification:2.2.0` as the `semanticProfile` identifier in AtlasData.
That couples two independent concerns: the published meaning of semantic tags and the
inference task used to produce them. It also made the in-memory `SemanticProfile` a
hard-coded composition rather than a versioned resource.

A published document needs to identify the vocabulary required to interpret its semantic
tags. It does not need to know which prompt, model, qualification cascade, or classification
task produced those tags.

## Decision

Introduce independently versioned semantic profile resources. The functional-safety profile
uses the stable id `functional-safety`; the current profile version is `1.0.0`. A profile
composes independently versioned ontology dimensions and therefore defines the meaning and
encoding context of published semantic tags.

`semantic-profile-classification` remains a separately versioned inference task. Current task
resources reference a semantic profile and may select the subset of profile dimensions that
the task itself infers. This permits role semantics to remain a focused task while role
relation types remain part of the published functional-safety profile.

AtlasData and public semantic annotation manifests reference only the semantic profile, for
example `functional-safety:1.0.0`. They do not persist a classification-task reference.
Qualification and run artifacts continue to identify their classification task and version.

AtlasData task-style references such as `semantic-profile-classification:2.4.0` are not
semantic-profile identifiers and are rejected. No compatibility mapping is provided for these
pre-contract artifacts; affected AtlasData must be regenerated with an explicit profile reference.

## Consequences

- published semantic tags are independent of inference implementation and task version;
- semantic profiles can be reused by multiple classification or extraction tasks;
- classification tasks can evolve without changing the meaning of already published tags;
- ontology composition changes are represented by semantic-profile versions;
- AtlasData has no dependency on semantic-classification task contracts;
- the workflow option is named `include_semantic_classification`, describing execution rather
  than the profile resource it consumes.

## Related decisions

- ADR 0051: Multidimensional semantic classification
- ADR 0062: Separate semantic taxonomies from semantic tasks
- ADR 0065: Semantic ontology definitions
- ADR 0083: Separate deterministic document workflow from semantic qualification
