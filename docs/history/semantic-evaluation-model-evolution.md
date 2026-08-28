# Evolution of the semantic evaluation model

> **Document status:** Historical rationale. This document records the findings that led to ADR 0007 and ADR 0008. It is not an active implementation plan.

## Background

The first complete qualification matrix for semantic-role classification showed that model selection was not the dominant limitation. The more important weaknesses were the flat semantic model and the construction of the reviewed reference data.

The original review process started from automatically generated proposals. This made the resulting corpus useful for regression testing, but it also introduced an anchoring risk: reviewers could accept a plausible proposal without independently evaluating every alternative.

## Findings

### Independent semantic dimensions had been mixed

The former role list combined at least two different concerns:

- the linguistic function of a statement, such as requirement, recommendation, permission, definition, explanation, rationale, or example;
- the structural function of a clause, such as scope, terminology, system requirements, verification, validation, configuration management, or documentation.

A clause can be a requirement and belong to a verification section at the same time. These classifications are orthogonal rather than competing labels.

### Document structure strongly influences interpretation

For technical standards, the position of a clause in the document hierarchy carries information that is not present in the clause text. This explained why structure-aware prompts outperformed content-only prompts in the initial experiments.

### A flat role list was not extensible enough

A domain-independent document structure and domain-specific lifecycle structures need separate taxonomies. Functional Safety, Cybersecurity, Polarion exports, Railway TSI documents, and other document families cannot be forced into one fixed role enumeration.

## Resulting architecture

The findings were implemented through:

- [ADR 0007](../architecture/adr/0007-structural-taxonomy-and-context-model.md), which introduced the multidimensional `StructuralProfile`;
- [ADR 0008](../architecture/adr/0008-semantic-ontology-profile-and-classification-model.md), which removed `Clause.semantic_roles` and `SemanticRole` without a compatibility layer and introduced independent semantic dimensions.

The current architecture is described in:

- [Domain model](../architecture/domain-model.md)
- [Structural classification](../architecture/structural-classification.md)
- [Evaluation services](../architecture/evaluation-services.md)

## Remaining research question

The long-term question remains how technical standards can be represented so that relationships across standards and Knowledge Domains can be identified and explained reliably. Current roadmap work for this goal is maintained under [IntelliDoc refactoring](../roadmap/intellidoc-refactoring.md), not in this historical document.
