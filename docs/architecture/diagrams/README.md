# Diagram catalog

All architecture diagrams are stored as rendered SVG and editable draw.io source. Documentation embeds SVG; architectural changes should update both files in the same commit.

## Reading the catalog

The diagrams are intentionally scoped views, not exhaustive inventories of every class, service, port, adapter, artifact, configuration option, and runtime concern mentioned in the accompanying documents. A document is authoritative for the complete architectural topic; its diagram highlights the relationships that are most useful for orientation. Where a diagram is deliberately selective, the embedding document states its scope and points to a more detailed view when one exists.

The two broad UML baselines are:

- **Overall component architecture** for the major inbound adapters, application capabilities, domain core, outbound ports, infrastructure adapters, and external systems.
- **Canonical domain model class diagram** for the stable aggregate and value-object relationships.
- **Application architecture class diagram** for principal services, outbound ports, and infrastructure adapters.

The former multi-view current-architecture class diagram has been split so domain evolution and application-boundary evolution can be maintained independently.

## Current architecture

| Diagram | SVG | Editable source |
|---|---|---|
| Architecture overview | [SVG](svg/architecture-overview.svg) | [draw.io](drawio/architecture-overview.drawio) |
| Component model | [SVG](svg/component-model.svg) | [draw.io](drawio/component-model.drawio) |
| Overall component architecture (UML) | [SVG](svg/overall-component-architecture.svg) | [draw.io](drawio/overall-component-architecture.drawio) |
| System context | [SVG](svg/system-context.svg) | [draw.io](drawio/system-context.drawio) |
| Ports and adapters | [SVG](svg/ports-and-adapters.svg) | [draw.io](drawio/ports-and-adapters.drawio) |
| Domain model | [SVG](svg/domain-model.svg) | [draw.io](drawio/domain-model.drawio) |
| Canonical domain model class diagram (UML) | [SVG](svg/canonical-domain-model-class-diagram.svg) | [draw.io](drawio/canonical-domain-model-class-diagram.drawio) |
| Application architecture class diagram (UML) | [SVG](svg/application-architecture-class-diagram.svg) | [draw.io](drawio/application-architecture-class-diagram.drawio) |
| Taxonomy to ontology classification flow | [SVG](svg/taxonomy-ontology-classification-flow.svg) | [draw.io](drawio/taxonomy-ontology-classification-flow.drawio) |
| Qualification cascade | [SVG](svg/qualification-cascade.svg) | [draw.io](drawio/qualification-cascade.drawio) |
| StructuralContext and scope reach | [SVG](svg/structural-context-scope-reach.svg) | [draw.io](drawio/structural-context-scope-reach.drawio) |
| Processing pipeline | [SVG](svg/processing-pipeline.svg) | [draw.io](drawio/processing-pipeline.drawio) |
| Workflow orchestration | [SVG](svg/workflow-orchestration.svg) | [draw.io](drawio/workflow-orchestration.drawio) |
| Artifact lineage | [SVG](svg/artifact-lineage.svg) | [draw.io](drawio/artifact-lineage.drawio) |
| Evaluation architecture | [SVG](svg/evaluation-architecture.svg) | [draw.io](drawio/evaluation-architecture.drawio) |
| LLM integration | [SVG](svg/llm-integration.svg) | [draw.io](drawio/llm-integration.drawio) |
| MCP architecture | [SVG](svg/mcp-architecture.svg) | [draw.io](drawio/mcp-architecture.drawio) |
| Runtime and deployment | [SVG](svg/runtime-deployment.svg) | [draw.io](drawio/runtime-deployment.drawio) |
| Relationship-mapping target | [SVG](svg/relationship-mapping-target.svg) | [draw.io](drawio/relationship-mapping-target.drawio) |

## Specialized and historical diagrams

The directory also contains workflow, review, workspace, multipart, Doorstop, content-boundary, AtlasData lifecycle, and ADR-specific diagrams. ADR diagrams document the decision at the time it was accepted and should not be silently rewritten to describe a later architecture.
