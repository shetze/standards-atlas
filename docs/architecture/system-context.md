# System context

![System context](diagrams/svg/system-context.svg)

Standards Atlas sits between controlled technical publications and downstream automated engineering processes. It captures standards, technical specifications, and other strongly structured technical texts as canonical **EngineeringDocuments** and enriches them so that both document structure and engineering meaning can be consumed by machines without losing provenance.

Inputs include private source publications, public AtlasData baselines, catalogs, Knowledge Domain configuration, domain-specific OWL TBoxes, and human review decisions. Deterministic processing first captures document structure and taxonomy. Qualified LLM-assisted processing then identifies abstract semantic functions and domain knowledge. Taxonomy, semantic context, structural position, provenance, and qualification evidence form the Standards Atlas context layer (CBox); domain TBoxes provide the formal vocabulary from which clause-level ABox assertions are derived.

Clause-level formal projections accumulate into an engineering knowledge base that can relate independently authored standards and different engineering domains through shared or mapped semantics while preserving source identity. This knowledge-centric view complements the document-centric `EngineeringDocument` representation.

Retrieval and serving are downstream concerns. Formal knowledge can be queried directly or indexed through lexical, vector, RAG, or GraphRAG mechanisms and then exposed to interactive chat, MCP clients, APIs, Doorstop traceability, relationship analysis, or other applications. These are rebuildable views and access paths rather than canonical storage.

Source publications remain authoritative and protected according to their licensing constraints. Every generated semantic assertion retains links through extraction provenance and qualification or review evidence to its originating clause and source. LLMs are qualified analysis components where deterministic methods are insufficient; the architecture does not depend conceptually on a particular LLM or inference technique.

The context diagram identifies actors, external systems, and protected-content boundaries. Internal application services and repositories are intentionally delegated to the component, class, pipeline, and deployment views.
