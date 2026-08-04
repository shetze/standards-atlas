# Processing pipeline

![Processing pipeline](diagrams/svg/processing-pipeline.svg)

The diagram shows the principal artifact progression and review gates. The text additionally covers validation contracts, transformation ledger entries, layout evidence, reference resolution, invalidation rules, and publication variants that are intentionally not expanded into separate nodes.

The document pipeline converts controlled publications into canonical engineering knowledge through persisted, inspectable stages.

## Stages

1. **Catalog resolution** selects document families, parts, profiles, source files, page ranges, and publication targets.
2. **Extraction** converts selected PDF content through Docling and validates the extracted-document boundary.
3. **Normalization** applies ordered deterministic steps for item mapping, page furniture, headings, lists, layout evidence, hyphenation, visual ownership, methods, techniques, and reference candidates.
4. **Reference structure** imports or generates AtlasData-compatible structural baselines.
5. **Alignment** proposes mappings from normalized ranges to reference clauses.
6. **Human review** records alignment corrections and baseline decisions as separate artifacts.
7. **Construction contract** freezes the reviewed inputs and verifies coverage before aggregate construction.
8. **Engineering document construction** creates canonical clauses, content, evidence, profiles, and lineage.
9. **Reference resolution** links clause references that can be resolved within available documents or knowledge domains.
10. **Publication** creates Markdown, composed Markdown, and Doorstop projections.
11. **Evaluation and enrichment** samples canonical clauses, generates model proposals, performs review, and may publish accepted annotations or relations.

## Normalization contract

Normalization is an ordered pipeline of explicit transformation steps. Each step receives a typed document, returns a typed document, and records deterministic ledger entries. The order is part of the contract because later steps may depend on evidence established earlier. LLMs are not part of the canonical normalization path.

## Review gates

Alignment review and AtlasData baseline review are blocking gates. The workflow may generate review material, but it must not silently treat a machine proposal as a reviewed decision. Evaluation follows the same rule: proposals and consensus reports are not canonical annotations.

## Replacement and invalidation

A changed source selection invalidates extraction and all descendants. A changed normalization implementation invalidates normalized descendants but not the source. A changed baseline invalidates alignment and construction. Renderer-only changes invalidate exports. The workflow report explains these derivations instead of relying only on timestamps.
