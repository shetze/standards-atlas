# Core concepts

## Standard family

A logical standard such as IEC 61508 or ISO 26262. A family may contain one or many physical publications and parts.

## Physical source document

A specific PDF with provenance, publication metadata, and optional page selection. One logical family may be assembled from several physical sources.

## Extracted document

Docling's source-oriented representation. It preserves layout and content evidence but is not the canonical domain model.

## Normalized document

A deterministic, lossless normalization of extracted content. It stabilizes headings, lists, page furniture, visual references, and source anchors before semantic processing.

## AtlasData

The public structural baseline used to describe expected clauses, headings, types, and public annotations. AtlasData has an explicit lifecycle and is not treated as copyrighted clause content.

## Alignment

A mapping between detected source references and expected AtlasData structure. Automatic alignment is provisional until reviewed.

## EngineeringDocument

The canonical, adapter-neutral domain representation. It contains clauses, structured content blocks, multidimensional semantic classifications, annotations, relations, and source evidence.

## Knowledge domain

A catalog-level model of standards and relationships. It expresses families, sectors, supersession, adaptation, and the hierarchy used by downstream exports.

## Workflow gate

A deliberate pause where human judgment is required. Standards Atlas does not silently turn uncertain extraction or alignment into an authoritative result.
