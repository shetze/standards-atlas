# Changelog

This changelog summarizes the architectural refactoring of Standards Atlas. It intentionally consolidates the detailed Git history into a compact record of the major design transitions and externally relevant capabilities. Individual fixes, test-only changes, data corrections, and intermediate refactoring commits are represented by the milestone in which they became part of the architecture.

## Unreleased — Refactoring consolidation (2026-08-20 to 2026-08-28)

### Semantic architecture and qualification

- Finalized the separation of **structural taxonomy**, **semantic classification**, and **formal ontology**. Deterministic structural context is materialized before LLM-assisted semantic processing, while OWL remains the formal semantic model rather than a classification API.
- Consolidated the public semantic API around `SemanticProfile`, semantic dimensions, and semantic classification; removed the former ontology-classification terminology from workflow, CLI, and application services.
- Versioned **Semantic Profiles independently from classification tasks**. Classification tasks now select dimensions from a referenced profile, while AtlasData and public semantic annotations refer to the profile rather than to an inference task.
- Aligned production semantic classification with the same versioned task and prompt contracts used by qualification, while retaining a single-model production execution policy.
- Split applicability into explicit **presence** and optional **subtype** semantics, including independent cascade resolution, model eligibility, golden-set evaluation, and production persistence.
- Replaced the former responsibility dimension with **role semantics** and structured actor–relation-class–target tuples; separated role-presence qualification from relation-tuple consensus and added golden-corpus evaluation.
- Made multidimensional qualification cascade-aware per dimension, including majority-based knowledge escalation, dimension-specific model eligibility, challenger qualification, reproducible HITL evidence, and immutable run archives.
- Preserved structural evidence, exact task/prompt/ontology inputs, model identity, analysis provenance, and qualification artifacts so runs can be reproduced and audited.

### Formal semantics and GraphRAG foundation

- Introduced a provider-neutral **Formal Semantic & Context Model** with versioned Standards Atlas Core and Functional Safety OWL ontologies.
- Added deterministic **ABox/CBox projection** from canonical `EngineeringDocument` data, covering document structure, Knowledge Domains, semantic taxonomy context, applicability, normative context, lineage, and resolved relations.
- Added ontology-guided concept and relation extraction constrained to declared OWL classes and properties, with confidence and provenance kept in rebuildable semantic-extraction artifacts rather than canonical documents.
- Integrated semantic extraction into qualification, including ontology-conformance checks, per-clause failure isolation, bounded retries/timeouts, progress reporting, undeclared-term diagnostics, and archival of extraction evidence.
- Refined the Functional Safety ontology from qualification evidence with explicit part/whole relations and additional system, requirement, specification, quantity, fault, error, and failure concepts.

### Document, family, table, and publication model

- Separated canonical **physical documents** from rebuildable **family publication views**. Multipart standards are composed in `.atlas/work/composed-documents`; `.atlas/data/documents` contains only physical parts.
- Added manifest-driven family-aware Docling onboarding with per-part publication metadata and part-aware clause identity.
- Promoted tables to first-class document structure and implemented the table pipeline: structural capture → deterministic `NormalizedTable` → structured `KnowledgeTable` mapping → provider-neutral retrieval projection.
- Added table-aware semantic extraction and provenance handling for large standards tables such as IEC 61508 technique/measure matrices.
- Hardened hierarchical Doorstop/Markdown publication, identifier generation, cross-document references, structural scope relations, and distinction between headings and document titles.
- Kept generated publication views rebuildable and qualification focused on physical source documents rather than aggregate family documents.

### Workflow, storage, schemas, and architecture

- Established explicit generated-data lifecycle boundaries: persistent machine state in `.atlas/data`, disposable cache data in `.atlas/cache`, rebuildable/intermediate workflow state in `.atlas/work`, and human-facing review/output under `local/`.
- Unified workflow task selection and typed manifest handling; made structural/document stages deterministic and assigned LLM-backed semantic classification explicitly to qualification where appropriate.
- Hardened workflow recovery, overwrite/fresh semantics, model lifecycle management, qualification limits, and Doorstop workspace handling.
- Established bounded schema compatibility: current-only writers, explicitly versioned persistent contracts, visible deprecation for supported readers, and no compatibility promise for disposable cache/work formats.
- Consolidated the ports-and-adapters architecture, package boundaries, CLI modules, qualification/proposal/normalization/alignment/Docling components, shared serialization/reporting infrastructure, ADRs, and UML documentation.

## 0.8.2 — Architecture policy baseline (2026-08-20)

- Introduced dimension-specific model eligibility and challenger qualification for the semantic qualification cascade.
- Established the storage lifecycle, taxonomy/task separation, schema compatibility policy, explicit ontology application boundary, structural-context taxonomy stage, and deterministic taxonomy → semantic/ontology ownership model that the subsequent refactoring completed.
- Strengthened structural reference/scope capture and reproducible qualification evidence.

## 0.8.1 — Modular qualification baseline (2026-08-05)

- Completed the first broad modularization of CLI, qualification, proposal generation, normalization, alignment, Docling processing, and shared infrastructure.
- Evolved semantic evaluation from a single role classifier into a multidimensional profile covering statement function, knowledge, process, applicability, and role/responsibility semantics.
- Added dimension-aware consensus/cascade processing, intermediate escalation, HITL review, structural-evidence fusion, scope inheritance, and public semantic gold annotations.
- Added visual-formula preservation and MCP-assisted formula transcription with provenance.
- Introduced structured table semantics and semantic-evaluation eligibility as the precursor to the later first-class table pipeline.

## 0.7.x — Canonical document and qualification architecture (2026-07-23 to 2026-08-04)

- Established deterministic `NormalizedDocument` and canonical `EngineeringDocument` contracts, AtlasData governance, workspace/publication architecture, and structured Markdown/Doorstop export.
- Added provider-independent LLM infrastructure, managed RamaLama lifecycle/GPU coordination, semantic evaluation services, and a secure interoperable MCP adapter.
- Built the reproducible evaluation stack: representative corpora, annotation contracts, proposal diagnostics, clause-reference context, qualification metrics, Codex integration, multidimensional qualification matrices, adaptive execution, consensus, and HITL workflows.
- Enforced ports-and-adapters dependency direction, narrowed service APIs, removed legacy `Clause.text` compatibility, modularized workflow/CLI boundaries, and synchronized ADR/UML documentation.
- Added deterministic internal and cross-document clause-reference materialization and normative inference from document structure.

## 0.6.x — Pipeline and composition foundation (2026-07-13 to 2026-07-21)

- Introduced structured clause content, reproducible Docling PDF extraction, deterministic normalization, clause-reference candidate detection, deterministic AtlasData alignment, and HITL alignment review.
- Added multipart-document support, document composition, semantic-role onboarding, and structured Markdown export.
- Consolidated the Python 3.13 / 0.6 architecture around a canonical engineering-document pipeline and AtlasData compatibility.

## Initial architecture — Canonical domain model (2026-07-07 to 2026-07-11)

- Created the Python project and AtlasData adapter, then introduced the canonical engineering-document domain model and compiler-style architecture.
- Added importer/exporter ports, application services, transformation pipelines, file-backed repositories, round-trip workflows, and the first annotation model.
- Established the architectural direction that later evolved into the current ports-and-adapters, deterministic preprocessing, qualification, and formal-semantics pipeline.
