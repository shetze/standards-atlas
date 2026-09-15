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
10. **Context enrichment (`CONTEXT_ENRICHMENT`)** materializes routing and deterministic subject context. Accepted applicability is a separate qualified enrichment and is adopted explicitly; it is not a clause-classification label.
11. **Context projection (CBox)** combines Knowledge Domain, deterministic taxonomy, structural position, routing/subject context, accepted applicability, provenance, and qualification evidence into explicit context for formal interpretation.
12. **Assertion proposal extraction, structured projection and unification** write run-scoped `DocumentKnowledgeProposal` artifacts containing source-bound entity and assertion proposals against the selected domain-specific OWL TBox/RBox vocabulary. Slice 5B grounds every proposed prose entity and assertion through an exact unique quote resolved to `Clause.plain_text`; absent or repeated quotes become explicit proposal violations and never fall back to whole-clause evidence. Slice 6A projects supported portable matrices into the same contract, Slice 6B deterministically unifies those proposal runs using normalized labels plus compatible ontology types while preserving input-run hashes/provenance, and Slice 6C reifies qualified IEC 61508 technique recommendations so technique, SIL and recommendation level remain separate source-bound dimensions. Normative force is assertion-local. Confidence, rationale, violations, attempts and failures remain proposal metadata. Only qualified/adopted assertions become canonical `DocumentKnowledge`; every accepted assertion retains source and evidence anchors.
13. **Assertion qualification** compares non-canonical proposals against versioned assertion golden suites before any adoption. Slice 7A measures entity and assertion precision/recall plus predicate, normative-force, grounding, and exact-assertion accuracy. Golden suites are explicitly partitioned as `development` or `holdout`, bind exact formal-ontology versions, and use exact source spans rather than copied source text. Slice 7B adds a threshold-free Efficient → Verify → Escalate execution path: every eligible prose clause is independently verified, including empty Efficient outputs so missing assertions can be detected, and only disputed clauses are escalated. The cascade persists routing evidence and stage proposal identities but cannot adopt knowledge. Automatic-adoption policy follows in 7C.
14. **Knowledge integration and relationship enrichment** resolves internal and cross-document targets and relates accepted assertions across documents and domains while preserving unresolved evidence and source identity.
15. **Retrieval and serving projections** may build lexical, vector, RAG, or GraphRAG indexes or graph-query services. These are rebuildable access mechanisms, not canonical storage.
16. **Interfaces and applications** expose the knowledge through chat, MCP, APIs, Doorstop traceability, relationship analysis, heatmaps, and future consumers without making any one application a pipeline purpose.
17. **Publication** creates Markdown, composed Markdown, and Doorstop projections without changing canonical knowledge ownership.
18. **Evaluation and qualification** operate as separate workflows for datasets, analyzer qualification, regression evidence, and HITL review. Probabilistic outputs remain proposals until the explicit adoption boundary.

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

The mandatory document path is `ENRICH → TAXONOMY → CONTEXT_ENRICHMENT`.
`ENRICH` preserves content and evidence, `TAXONOMY` derives deterministic structural
context, and `CONTEXT_ENRICHMENT` materializes routing and subject context. Applicability
qualification and formal assertion extraction are separate qualified workflows; neither
reconstructs the retired statement/knowledge/process/role clause-classification model.

Imported reviewed knowledge may populate accepted assertion or applicability state only
through the explicit adoption boundary with preserved provenance.

## Architectural layers

The pipeline can be understood as a set of responsibilities rather than as one fixed technology stack:

```text
Acquisition
    -> controlled source publications
Canonical representation
    -> EngineeringDocuments
Context enrichment
    -> deterministic taxonomy + routing/subject context + accepted applicability + CBox
Knowledge representation and integration
    -> evidence-backed entities/assertions + domain TBox/RBox projection + provenance
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
