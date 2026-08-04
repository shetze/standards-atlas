# Core concepts

## Standard family and physical document

A **standard family** is the logical standard represented in the catalog. A family can contain several **physical source documents**, such as individual parts or editions. Physical documents retain their own provenance and page selection.

## Extracted and normalized documents

The **extracted document** is Docling-native source evidence. The **normalized document** is a deterministic and lossless representation used by subsequent stages. Normalization records transformations rather than silently rewriting content.

## AtlasData and alignment

**AtlasData** is the reviewable public structural baseline: identifiers, headings, clause types and copyright-safe annotations. **Alignment** maps references detected in normalized source content to that baseline. Automatic alignment is a proposal until a reviewer accepts or overrides it.

## EngineeringDocument and Clause

`EngineeringDocument` is the canonical domain representation. A `Clause` contains structured `content`, source evidence, references, annotations and an optional multi-dimensional `StructuralProfile`. The former one-dimensional `SemanticRole` and `Clause.semantic_roles` model no longer exists.

## StructuralProfile

A structural profile classifies independent dimensions instead of forcing a clause into one role. Dimensions can describe, for example, normative status, statement function, lifecycle context, evidence relevance or document region. Taxonomies are knowledge-domain specific and must not be inferred from keywords alone when evidence is insufficient.

## Knowledge domain and hierarchy

A **knowledge domain** groups standards and relationships for a field such as functional safety. A configured hierarchy determines composed Doorstop publication, while the filesystem remains an implementation detail.

## Review gate

A **review gate** is an intentional workflow pause. Standards Atlas preserves uncertainty and requires a human decision rather than publishing weak extraction or alignment as authoritative data.
