# Glossary

**Alignment** — mapping source candidates to expected clause structure.  
**Annotation** — derived or maintained knowledge associated with a clause.  
**AtlasData** — public structural baseline and exchange format.  
**Clause** — one logical unit in an engineering document.  
**Content block** — ordered structured content such as paragraph, list, table, or figure.  
**DocumentKey** — stable identifier for a persisted document or pipeline artefact.  
**EngineeringDocument** — canonical adapter-neutral document aggregate and source of identity for derived semantic and publication projections.  
**Family** — logical standard composed from one or more physical documents.  
**Knowledge domain** — catalog model relating families, sectors, and standards relationships.  
**Lineage** — recorded dependency chain from source through transformations and reviews.  
**NormalizedDocument** — lossless stable representation used before semantic alignment.  
**Physical source** — one actual publication file with provenance and selection metadata.  
**Profile** — named catalog selection of families.  
**Review gate** — workflow pause requiring a human-approved artefact.  
**CBox** — Standards Atlas context layer combining Knowledge Domain, taxonomy, semantic, structural, provenance, and qualification context for formal assertions; an architectural convention, not a native OWL box.  
**TBox** — OWL terminology defining domain concepts, classes, and their semantic constraints.  
**ABox** — OWL assertions about concrete individuals derived from EngineeringDocument clauses and their context.  
**RAG** — retrieval-augmented generation over derived indexes of EngineeringDocument knowledge.  
**GraphRAG** — graph-oriented retrieval-augmented generation over formal entities and relationships derived from EngineeringDocuments.  
**Engineering knowledge base** — knowledge-centric view that integrates evidence-backed formal assertions across EngineeringDocuments while preserving source identity and provenance.  
**Qualified semantic analysis** — semantic inference performed by an analyzer that has been evaluated for its task and whose accepted outputs retain provenance and qualification evidence; LLMs are one possible implementation.  
**Retrieval and serving layer** — rebuildable lexical, vector, graph, RAG, or GraphRAG access structures and services over canonical documents and formal knowledge; not canonical persistence.  
**Evidence-backed assertion** — derived semantic assertion that can be traced through extraction and qualification evidence to its originating clause, EngineeringDocument, and source publication.  
