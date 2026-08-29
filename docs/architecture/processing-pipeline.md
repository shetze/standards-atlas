# Processing pipeline

![Processing pipeline](diagrams/svg/processing-pipeline.svg)

The diagram shows the principal artifact progression and review gates. The text additionally covers validation contracts, transformation ledger entries, layout evidence, reference resolution, invalidation rules, and publication variants that are intentionally not expanded into separate nodes.

The document pipeline converts controlled publications into canonical EngineeringDocuments and then into formal, retrieval-ready engineering knowledge through persisted, inspectable stages.

## Stages

1. **Catalog resolution** selects document families, parts, profiles, source files, page ranges, and publication targets.
2. **Extraction** converts selected PDF content through Docling and validates the extracted-document boundary. Known `visual_only` formula regions are then rendered deterministically from the source PDF through the dedicated PyMuPDF formula-visual adapter; the adapter does not discover formulas.
3. **Normalization** applies ordered deterministic steps for item mapping, page furniture, headings, lists, layout evidence, hyphenation, visual ownership, methods, techniques, and reference candidates.
4. **Reference structure** imports or generates AtlasData-compatible structural baselines.
5. **Alignment** proposes mappings from normalized ranges to reference clauses.
6. **Human review** records alignment corrections and baseline decisions as separate artifacts.
7. **Construction contract** freezes the reviewed inputs and verifies coverage before aggregate construction.
8. **Engineering document construction (`ENRICH`)** creates canonical clause content, evidence, reference mentions, and lineage. It does not classify structure or semantic meaning.
9. **Structural taxonomy (`TAXONOMY`)** deterministically materializes `StructuralProfile` and `StructuralContext`, including hierarchy, node/leaf role, ancestor context, sibling sequence position, contextual node content, structural reference edges, and structural scope reach (for example `this clause`, following sibling clauses, or a scope-heading subtree).
10. **Semantic classification (`SEMANTIC_ENRICHMENT`)** applies the qualified production classifier to clause content plus the complete structural context and assigns statement functions, knowledge kinds, process functions, applicability functions, and role-relation types.
11. **Context projection (CBox)** combines Knowledge Domain, deterministic taxonomy, semantic functions, structural position, provenance, and qualification evidence into explicit context for formal interpretation.
12. **Formal semantic projection** applies the selected domain-specific OWL TBox/RBox vocabulary to derive clause-level ABox assertions while preserving CBox context, source identity, extraction provenance, and qualification evidence. Context describes interpretation; ABox assertions represent domain knowledge.
13. **Knowledge integration and relationship enrichment** resolves internal and cross-document targets and relates knowledge across documents and domains through shared or mapped semantics while preserving unresolved evidence and source identity.
14. **Retrieval and serving projections** may build lexical, vector, RAG, or GraphRAG indexes or graph-query services. These are rebuildable access mechanisms, not canonical storage.
15. **Interfaces and applications** expose the knowledge through chat, MCP, APIs, Doorstop traceability, relationship analysis, heatmaps, and future consumers without making any one application a pipeline purpose.
16. **Publication** creates Markdown, composed Markdown, and Doorstop projections without changing classification ownership.
17. **Evaluation and qualification** operate as separate workflows for datasets, analyzer qualification, regression evidence, and HITL review; they establish whether probabilistic semantic components are suitable for production use but do not replace the production `SEMANTIC_ENRICHMENT` stage.

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

The production path has one mandatory direction: `ENRICH → TAXONOMY → SEMANTIC_ENRICHMENT`.
`ENRICH` preserves content and evidence, `TAXONOMY` derives deterministic structural
context, and `SEMANTIC_ENRICHMENT` interprets semantic meaning. The semantic classification stage receives the
materialized structural context and therefore never has to reconstruct hierarchy from
prose. Automatic modal-verb heuristics are not permitted outside `SEMANTIC_ENRICHMENT`.

Semantic qualification remains a separate evaluation workflow used to select and validate
the production classifier. Imported reviewed/public semantic annotations may populate
ontology fields directly because they are explicit evidence, not automatic inference.

## Architectural layers

The pipeline can be understood as a set of responsibilities rather than as one fixed technology stack:

```text
Acquisition
    -> controlled source publications
Canonical representation
    -> EngineeringDocuments
Context enrichment
    -> deterministic taxonomy + qualified semantic functions + CBox
Knowledge representation and integration
    -> domain TBox/RBox + clause ABoxes + provenance
Retrieval and serving
    -> lexical/vector retrieval + RAG + GraphRAG + graph queries
Interfaces
    -> chat + MCP + APIs
Applications
    -> traceability + cross-standard analysis + heatmaps + QA + future use cases
```

Only the upper layers through canonical representation define document identity. Formal knowledge, retrieval structures, interfaces, and applications are derived from or consume that identity and can evolve independently.

## Semantic trust contract

Semantic inference is not accepted merely because an analyzer can produce syntactically valid output. Production semantic components must operate under explicit contracts and qualification evidence. Each accepted assertion must preserve a traceable path of the form `assertion -> extraction/provenance -> clause -> EngineeringDocument -> source publication`. This requirement applies whether the analyzer is an LLM, another statistical model, or a future non-LLM technique.
