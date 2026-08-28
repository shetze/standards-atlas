# Knowledge Domains

## Purpose

Knowledge Domains classify engineering knowledge independently from source-document families and publication technologies. They provide the domain vocabulary used to organize clauses, taxonomies, relationships, evaluation corpora, and future MCP capabilities.

A Knowledge Domain is not a directory format, a Doorstop hierarchy, or an exporter configuration. Those are projections or operational selections built from the catalog and canonical document model.

## Current model

Knowledge Domains are declared in `manifests/standards.yaml` and may form a hierarchy through their optional `parent` relation. Standard families, lineages, and profiles can reference one or more domains.

Examples from the current catalog include:

- Safety
- Functional Safety
- Software Engineering
- Risk Management
- Cybersecurity
- Information Security
- Software Testing
- Standardization
- Technical Writing

A document can belong to several Knowledge Domains. This is intentional: a railway software standard may contribute simultaneously to Functional Safety, Software Engineering, and a railway industry-sector classification.

## Distinction from related concepts

| Concept | Responsibility |
|---|---|
| **Knowledge Domain** | Classifies the engineering subject matter and owns domain-specific taxonomies |
| **Industry sector** | Classifies the application context, such as railway or automotive |
| **Document family** | Groups one standalone document or a multipart standard and its physical sources |
| **Structural taxonomy** | Defines versioned categories used by `StructuralProfile` for a document family or Knowledge Domain |
| **Profile** | Selects catalog families for a workflow use case |
| **Doorstop hierarchy** | Defines a deterministic Doorstop publication tree |
| **Exporter** | Projects canonical documents into Markdown, Doorstop, or another target format |

These concepts can refer to one another but must not be collapsed into a single hierarchy.

## Canonical knowledge carried by clauses

Within an `EngineeringDocument`, clauses can carry:

- stable identity and hierarchy;
- structured content and source evidence;
- multidimensional structural profiles;
- multidimensional semantic classifications;
- normative or informative status;
- internal and external relations;
- provenance and transformation lineage.

Review files, evaluation runs, travelogues, and publication artefacts are related resources, but they are not embedded wholesale into the Knowledge Domain classification itself.

## Taxonomy ownership

Domain-specific categories are open, namespaced, and versioned. Functional Safety therefore does not become the implicit template for Cybersecurity or other domains. A clause may carry categories from multiple domain taxonomies when a cross-domain interpretation is intentional.

The small canonical section vocabulary remains separate from:

- document-family categories, such as ISO/IEC drafting structure, Polarion exports, or Railway TSI structure;
- Knowledge-Domain categories, such as Functional Safety lifecycle functions;
- linguistic and process-oriented semantic functions.

See [Structural classification](structural-classification.md) and [Domain model](domain-model.md).

## Publication and integration adapters

The canonical model is independent from publication technology. Implemented projections include:

- Markdown export;
- Doorstop document export and hierarchy publication.

The Formal Semantic & Context Model projects Knowledge Domains into explicit CBox context while preserving `EngineeringDocument` as the canonical document representation. Graph-oriented storage/query tooling, BASIL integration, and additional document classes remain adapter or roadmap concerns. An adapter may omit information that its target format cannot represent, but it must not redefine the canonical model.

## Travelogues and curated relationships

Travelogues are curated explanatory artefacts associated with the knowledge base. They complement generated document projections but are not clause content and are not automatically part of every exporter output.

Document-level relationships and lineages can be curated in the catalog. Clause-level references and semantic relations are represented in the canonical document model and can later support cross-standard relationship mapping.

## Architectural consequences

- Knowledge Domains stay stable when publication adapters change.
- New domains can add taxonomies without extending a central enum.
- Workflow profiles and Doorstop hierarchies remain explicit projections rather than alternate sources of truth.
- MCP capabilities can grow around the knowledge represented in domains without coupling the domain model to a particular client or transport.

Related decisions: [ADR 0007](adr/0007-structural-taxonomy-and-context-model.md) and [ADR 0008](adr/0008-semantic-ontology-profile-and-classification-model.md).


See also [Formal Semantic & Context Model](formal-semantic-context-model.md) and [ADR 0009](adr/0009-formal-semantic-model-and-owl-projection.md).
