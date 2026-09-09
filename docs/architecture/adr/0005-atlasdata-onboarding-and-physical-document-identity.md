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

## Accepted enrichment transport

An explicit `atlasdata-enrichments` companion (schema `1.1`) is stored at
`<AtlasData parent>/enrichments/<physical-key>.yaml`. This extends, rather than replaces, the
existing AtlasData adapter and text format. TOC tags continue to represent reviewed categories;
companions additionally represent generated hints, confirmed negatives, primary labels,
availability and decision provenance which the compact tags cannot express losslessly.

The manifest selects source file, physical part/supplement and edition. Each clause binds its
full reference and stable ID to the exact legacy MD5 of the existing AtlasData TOC record. The
internal heading is persisted for review, and structural/source/content SHA-256 fingerprints are
grouped separately under `fingerprints:`. A legacy reference year is not silently rewritten to the
manifest edition; both identities are checked. Missing source text is explicitly unverified, not
reconstructed or asserted equal. Clause records retain physical document order rather than sorting
by hash-derived clause IDs.

The existing import/part-selection pipeline builds physical skeletons without persisting a
synthetic family document. Companions then merge through the canonical attribute-group contract.
Generated values remain generated; current reviewed tags participate even in an existing workspace.
Two conflicting explicit authorities fail preflight. Structural content and its lifecycle status
are never rewritten by enrichment transfer. Selection is incremental: omission preserves state.

Original source-bearing context objects and raw provenance live in private immutable evidence
blobs, as defined by ADR 0013. Public companions contain categorical values, bounded context views
and centralized SHA-256 fingerprint references, not a copy of protected source text. Missing private values defer whole
context attributes rather than manufacturing empty conditions. Strict restoration rejects any
missing referenced private evidence. The canonical model remains the single document authority.

Qualification, canonical adoption and public persistence are separate explicit actions. The
initial companion implementation does not introduce automatic workflow publication or change
CBox framing and target-attribute isolation.

## Consequences
Qualification, corpus construction, provenance, and persistence operate on unambiguous physical documents. Family-wide outputs are composed later as views.
