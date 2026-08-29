# Architecture Decision Records

The ADR set describes the **current intended architecture** of Standards Atlas. During the active refactoring, obsolete intermediate decisions are removed instead of being retained as compatibility history; Git remains the history of how the architecture evolved.

Each ADR is deliberately broad enough to represent a durable architectural boundary rather than an individual implementation slice.

## Architectural orientation

All ADRs are interpreted against the project purpose: **Standards Atlas transforms strongly structured technical documents into a traceable, machine-processable Engineering Knowledge Base.** `EngineeringDocument` is the canonical document representation. Deterministic taxonomy and accepted abstract semantic functions provide interpretation context (CBox); domain ontologies provide TBox/RBox semantics; qualified clause-level extraction provides ABox knowledge. Retrieval technologies such as RAG and GraphRAG, interfaces such as Chat and MCP, and applications such as Doorstop export or heatmaps are replaceable consumers rather than the project purpose.

LLMs are qualified, replaceable analysis components for semantic work that cannot be derived reliably through deterministic processing. Every accepted derived assertion must remain traceable through provenance and qualification to its clause, canonical document, and source evidence.

| ADR | Decision |
|---|---|
| [0001](0001-architecture-principles-and-traceability.md) | Architecture principles and traceability |
| [0002](0002-canonical-document-and-provenance-model.md) | Canonical document and provenance model |
| [0003](0003-document-extraction-and-normalization-pipeline.md) | Document extraction and normalization pipeline |
| [0004](0004-visual-content-and-formula-evidence.md) | Visual content and formula evidence |
| [0005](0005-atlasdata-onboarding-and-physical-document-identity.md) | AtlasData onboarding and physical document identity |
| [0006](0006-multipart-families-and-publication-views.md) | Multipart families and publication views |
| [0007](0007-structural-taxonomy-and-context-model.md) | Structural taxonomy and context model |
| [0008](0008-semantic-ontology-profile-and-classification-model.md) | Semantic ontology, profile, and classification model |
| [0009](0009-formal-semantic-model-and-owl-projection.md) | Formal semantic model and OWL projection |
| [0010](0010-first-class-tables-and-structured-knowledge.md) | First-class tables and structured knowledge |
| [0011](0011-workflow-orchestration-and-stage-boundaries.md) | Workflow orchestration and stage boundaries |
| [0012](0012-semantic-qualification-and-evidence-model.md) | Semantic qualification and evidence model |
| [0013](0013-workspace-publication-and-artifact-lifecycle.md) | Workspace, publication, and artifact lifecycle |
| [0014](0014-schema-and-artifact-versioning-policy.md) | Schema and artifact versioning policy |
| [0015](0015-mcp-evaluation-boundary.md) | MCP evaluation boundary |

## Consistency review against the project purpose

The review found no architectural decision that must be reversed, but it exposed several wording-level tensions that are resolved by this revision:

- **Canonical document vs. knowledge base:** ADR 0002 previously described `EngineeringDocument` as the complete engineering knowledge state. It is now explicitly the canonical **document-centered** state; integrated OWL knowledge is a derived, cross-document view.
- **Semantic enrichments vs. ABox knowledge:** ADR 0008 now distinguishes accepted clause-level semantic/context enrichment from formal domain assertions. The former may be persisted with the canonical document; the latter belongs to the derived ABox/knowledge layer.
- **CBox vs. ABox:** ADRs 0007–0009 now state explicitly that structural taxonomy and abstract semantic functions describe interpretation context, whereas ABox assertions describe engineering-domain knowledge.
- **Qualification vs. production:** ADR 0011 previously risked making semantic work appear evaluation-only. Qualification remains the trust boundary for model-assisted inference, but accepted results feed a downstream knowledge-projection/serving stage.
- **Interfaces/applications vs. purpose:** Doorstop, Markdown, heatmaps, RAG/GraphRAG, Chat, and MCP are consistently treated as projections, retrieval mechanisms, interfaces, or applications rather than canonical models or fixed project goals.

These are clarifications of ownership and layering rather than reversals of the existing architecture.

## Reading order

For the system shape, start with ADR 0001 and ADR 0002. ADR 0003–0006 describe document ingestion, evidence, onboarding, and publication. ADR 0007–0010 define the structural and semantic model. ADR 0011–0015 define workflow ownership, qualification, artifact lifecycle, schema policy, and the external evaluation boundary.

## Decision lifecycle during refactoring

The project currently has no requirement to preserve ADR-level backward compatibility or previously published architecture states. When a decision becomes obsolete during the refactoring, the active ADR set is rewritten or consolidated so that it remains a compact description of the intended architecture. Historical decisions remain available through Git.

A new ADR is warranted when a change introduces or materially changes a durable architectural boundary, ownership rule, canonical contract, or evidence model. A local implementation choice or one step of a larger refactoring normally updates an existing ADR instead.

## Related documentation

- [Architecture overview](../README.md)
- [Processing pipeline](../processing-pipeline.md)
- [Domain model](../domain-model.md)
- [Structural classification](../structural-classification.md)
- [Formal semantic context model](../formal-semantic-context-model.md)
- [Diagram catalog](../diagrams/README.md)
