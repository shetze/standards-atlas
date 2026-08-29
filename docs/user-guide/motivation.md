# Motivation

Standards, technical specifications, and similar engineering texts contain valuable knowledge, but their document-oriented form makes systematic machine-assisted use difficult. Standards Atlas transforms these strongly structured texts into a **traceable, machine-processable engineering knowledge base** while preserving the source as canonical **EngineeringDocuments**.

The project does not prescribe one final application. Doorstop exports can seed software-quality traces, cross-domain relationships can be visualized as heatmaps, and interactive chat or MCP clients can explore the resulting knowledge. These are consumers of the knowledge base, not the purpose around which the document pipeline is designed.

## From documents to qualified knowledge

The central challenge is not merely to extract text, but to make engineering meaning machine-readable without losing evidence. Standards Atlas therefore separates deterministic document processing from semantic inference. Structural facts are derived deterministically wherever possible. Semantic analyses that go beyond reliable deterministic rules or pattern matching may use qualified LLMs or other analyzers behind explicit semantic contracts. LLMs are analysis components, not the architectural center of the system.

The result of semantic processing must remain **evidence-backed**. A derived assertion must be traceable through extraction provenance and qualification evidence to the clause, EngineeringDocument, and source publication from which it originated. This makes provenance, qualification, review, and persisted intermediate artifacts part of one common trust model rather than independent implementation concerns.

## Context and domain knowledge

Standards Atlas deliberately separates the context in which a document fragment is interpreted from the domain knowledge asserted by that fragment. Deterministic taxonomy, abstract semantic functions, structural position, Knowledge Domain, source identity, provenance, and qualification evidence form the **context layer (CBox)**. The CBox describes interpretation context; it is not itself the engineering-domain knowledge extracted from the clause.

Domain-specific OWL ontologies provide the **TBox** that defines relevant concepts, relations, and constraints. Clause-level **ABox** assertions express the extracted domain knowledge using that vocabulary while retaining their CBox context and source identity. This separation allows the same source statement to carry document context such as requirement function or actor context while independently asserting technical facts about activities, artifacts, hazards, techniques, or other domain concepts.

`EngineeringDocument` remains the canonical document representation. OWL is the formal representation of derived knowledge, not a replacement document format. CBox and ABox projections, Doorstop and Markdown publications, and retrieval indexes can therefore evolve or be regenerated without changing the identity of the source document.

## A cross-domain knowledge base

The accumulated formal projections form a knowledge-centric view across independently authored documents and engineering domains. Shared or mapped formal semantics make it possible to relate concepts and assertions across standards rather than limiting analysis to one document at a time. This cross-document and cross-domain integration is a primary capability of the Standards Atlas knowledge base.

RAG, GraphRAG, lexical or vector retrieval, and graph queries belong to the **retrieval and serving layer**. Chat, MCP, APIs, Doorstop traceability, heatmaps, quality-assurance workflows, and future applications consume that layer. No particular vector store, graph engine, LLM, protocol, or publication format defines the project.

Licensed source text can remain local while derived structure, provenance, and permitted projections are shared according to the applicable content policy.
