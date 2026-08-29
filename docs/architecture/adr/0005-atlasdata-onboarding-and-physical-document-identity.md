# ADR 0005: AtlasData Onboarding and Physical Document Identity

## Status
Accepted

## Goal alignment
Stable physical-document identity anchors the trace from knowledge assertions back to source publications. Family composition and cross-document knowledge integration are intentionally separate concerns: canonical identity remains document-centered, while family views and the knowledge base may span many physical documents.

## Context
AtlasData provides curated document structure and family metadata, while Docling provides extracted source evidence. Multipart standards require stable identity for each physical part.

## Decision
AtlasData onboarding is manifest-driven and produces canonical documents **per physical part**.

- Family manifests define family identity, parts, source mappings, hierarchy membership, and onboarding inputs.
- AtlasData heading/type information is treated as structural input; legacy type syntax may be parsed at the ingestion boundary but does not define the current semantic model.
- Skeleton generation from extracted headings is an onboarding aid, not a second canonical representation.
- Multipart family sources are split/resolved into physical part inputs before canonical `EngineeringDocument` construction.
- Annexes and other structural regions remain part of the owning physical document unless the source/manifest identifies them as separate physical documents.

## Consequences
Qualification, corpus construction, provenance, and persistence operate on unambiguous physical documents. Family-wide outputs are composed later as views.
