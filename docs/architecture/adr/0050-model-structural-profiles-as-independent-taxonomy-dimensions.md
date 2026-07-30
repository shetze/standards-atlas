# ADR 0050: Model structural profiles as independent taxonomy dimensions

## Status

Accepted

## Context

The original semantic-role vocabulary combines several independent concerns:

- language-level functions such as requirement, recommendation, and example;
- document structure derived from ISO/IEC drafting conventions;
- knowledge-domain structure such as the Functional Safety lifecycle;
- presentation and container concepts such as tables and annexes.

This works for an initial corpus of technical standards but does not scale to other
engineering document families. Polarion exports, Railway TSI documents, safety-case
artefacts, and future sources do not necessarily contain a normative main body,
verification chapter, management chapter, or another structure derived from the
ISO/IEC Directives. Functional Safety and Cybersecurity also have related but distinct
second-level lifecycle structures.

Annexes additionally carry an explicit normative or informative status. References add
another independent dimension because they may remain within one document or cross into
another document and knowledge graph.

## Decision

Add an optional, multi-dimensional `StructuralProfile` to each `Clause`.

The profile separates:

1. a deliberately small canonical section vocabulary shared by document families;
2. open, namespaced, versioned document-family categories;
3. open, namespaced, versioned KnowledgeDomain categories;
4. the explicit normative, informative, or unspecified status of annexes.

The canonical vocabulary does not prescribe an IEC-style normative main part. Unknown
or document-specific headings remain without a canonical section instead of being forced
into an unsuitable category.

Ship initial taxonomies for:

- documents following the ISO/IEC Directives, Part 2;
- Polarion exports;
- Railway TSI documents;
- Functional Safety;
- Cybersecurity.

These taxonomies are independent resources. A clause may carry categories from more
than one taxonomy when a cross-domain interpretation is intentional.

Extend `Relation` with an orthogonal `RelationScope`. Internal relations do not identify
a target document. External relations must identify `target_document_key`. The semantic
relation type remains independent from its scope.

The structural profile is independent from semantic statement classification. The temporary compatibility decision for `Clause.semantic_roles` was superseded by ADR 0051 and is no longer part of the implemented architecture.

## Consequences

- New document families and KnowledgeDomains can add taxonomies without modifying a
  central enum.
- Functional Safety does not become the implicit template for Cybersecurity.
- Annex force is represented explicitly and can participate in evaluation.
- Cross-document references become representable in the domain model.
- Existing persisted documents remain valid because structural profiles and relation
  scope metadata are optional or defaulted.
- Evaluation schemas and metrics can be split by dimension in a later slice without a
  flag-day migration.


## Amendment

ADR 0051 supersedes the temporary compatibility decision concerning `Clause.semantic_roles`. No flat semantic-role compatibility layer remains.
