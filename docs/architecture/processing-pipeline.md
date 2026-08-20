# Processing pipeline

![Processing pipeline](diagrams/svg/processing-pipeline.svg)

The diagram shows the principal artifact progression and review gates. The text additionally covers validation contracts, transformation ledger entries, layout evidence, reference resolution, invalidation rules, and publication variants that are intentionally not expanded into separate nodes.

The document pipeline converts controlled publications into canonical engineering knowledge through persisted, inspectable stages.

## Stages

1. **Catalog resolution** selects document families, parts, profiles, source files, page ranges, and publication targets.
2. **Extraction** converts selected PDF content through Docling and validates the extracted-document boundary. Known `visual_only` formula regions are then rendered deterministically from the source PDF through the dedicated PyMuPDF formula-visual adapter; the adapter does not discover formulas.
3. **Normalization** applies ordered deterministic steps for item mapping, page furniture, headings, lists, layout evidence, hyphenation, visual ownership, methods, techniques, and reference candidates.
4. **Reference structure** imports or generates AtlasData-compatible structural baselines.
5. **Alignment** proposes mappings from normalized ranges to reference clauses.
6. **Human review** records alignment corrections and baseline decisions as separate artifacts.
7. **Construction contract** freezes the reviewed inputs and verifies coverage before aggregate construction.
8. **Engineering document construction (`ENRICH`)** creates canonical clause content, evidence, reference mentions, and lineage. It does not classify structure or semantic meaning.
9. **Structural taxonomy (`TAXONOMY`)** deterministically materializes `StructuralProfile` and `StructuralContext`, including hierarchy, node/leaf role, ancestor context, sibling sequence position, contextual node content, and structural reference edges.
10. **Semantic ontology (`ONTOLOGY`)** applies the qualified production classifier to clause content plus the complete structural context and assigns statement functions, knowledge kinds, process functions, applicability functions, and responsibility functions.
11. **Reference resolution and relationship enrichment** resolves available internal and cross-document targets while preserving unresolved evidence for later interpretation.
12. **Publication** creates Markdown, composed Markdown, and Doorstop projections without changing classification ownership.
13. **Evaluation and qualification** operate as separate workflows for datasets, model qualification, regression evidence, and HITL review; they do not replace the production `ONTOLOGY` stage.

## Normalization contract

Normalization is an ordered pipeline of explicit transformation steps. Each step receives a typed document, returns a typed document, and records deterministic ledger entries. The order is part of the contract because later steps may depend on evidence established earlier. Visual formula preservation is deterministic input enrichment based only on source evidence and therefore does not introduce semantic inference. LLMs are not part of the canonical normalization path.

## Review gates

Alignment review and AtlasData baseline review are blocking gates. The workflow may generate review material, but it must not silently treat a machine proposal as a reviewed decision. Evaluation follows the same rule: proposals and consensus reports are not canonical annotations.

## Replacement and invalidation

A changed source selection invalidates extraction and all descendants. A changed normalization implementation invalidates normalized descendants but not the source. A changed baseline invalidates alignment and construction. Renderer-only changes invalidate exports. The workflow report explains these derivations instead of relying only on timestamps.

## Visual formula preservation

When Docling identifies a formula but cannot provide a semantic transcription, the extracted item retains its page and bounding box. The PDF formula-visual adapter clips that exact region, applies bounded padding, renders it as PNG, and attaches the result as a `VisualAsset`. The asset is propagated through normalization and engineering-document construction as part of the `FormulaBlock`. Missing source files or incomplete geometric evidence do not trigger guessed crops.

Semantic transcription is intentionally outside this stage. A future enrichment step may derive LaTeX, MathML, OpenMath, or another representation while retaining the original visual asset and source evidence.


## Taxonomy and ontology ownership

The production path has one mandatory direction: `ENRICH → TAXONOMY → ONTOLOGY`.
`ENRICH` preserves content and evidence, `TAXONOMY` derives deterministic structural
context, and `ONTOLOGY` interprets semantic meaning. The ontology stage receives the
materialized structural context and therefore never has to reconstruct hierarchy from
prose. Automatic modal-verb heuristics are not permitted outside `ONTOLOGY`.

Semantic qualification remains a separate evaluation workflow used to select and validate
the production classifier. Imported reviewed/public semantic annotations may populate
ontology fields directly because they are explicit evidence, not automatic inference.
