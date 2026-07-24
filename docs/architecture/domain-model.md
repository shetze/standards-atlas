# Domain model

![Domain model](diagrams/svg/domain-model.svg)

`EngineeringDocument` is the canonical aggregate. It is identified by a `DocumentKey` and contains ordered `Clause` objects plus document metadata and lineage.

A clause carries a stable identifier, source reference, clause type, semantic roles, heading, structured content blocks, relations, annotations, and adapter-neutral evidence. Content blocks distinguish paragraphs, lists, tables, figures, and other ordered material rather than flattening everything into Markdown.

Annotations are separate from source clauses. Their visibility controls whether they may be exported publicly. Relationships connect clauses and documents without making Doorstop or another target format part of the domain.

`NormalizedDocument`, candidate and alignment artefacts are pipeline contracts, not substitutes for the canonical aggregate.
