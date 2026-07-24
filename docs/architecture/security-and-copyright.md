# Security and copyright boundaries

![Content boundary](diagrams/svg/content-boundary.svg)

Standards Atlas processes documents that may be copyrighted or confidential. The architecture therefore distinguishes source-derived private artefacts from public structural metadata and deliberately publishable annotations.

Private PDFs, Docling JSON, normalized full text, alignment review material, and canonical documents containing source text remain local unless a controlled export permits them. AtlasData may contain metadata, structure, headings where permitted, types, and public annotations; it must not become an accidental copy of protected clause text.

Annotation visibility is explicit: `PUBLIC`, `LOCAL`, or `PRIVATE`. Exporters enforce visibility and target policy. Git ignore rules are a convenience, not the security boundary; users remain responsible for repository access, backups, and publication review.
