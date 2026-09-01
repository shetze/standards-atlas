# Ports and adapters

![Ports and adapters](diagrams/svg/ports-and-adapters.svg)

This diagram explains the dependency rule and adapter direction. It is intentionally less detailed than the second page of the [current architecture class diagram](diagrams/svg/current-architecture-class-diagram.svg), which names representative services, protocols, and implementations. Neither view attempts to enumerate every repository or command-specific composition path.

## Dependency rule

Standards Atlas uses hexagonal architecture as an enforceable dependency rule, not only as a diagram.

```text
inbound adapter -> application use case -> domain
                         |
                         v
                    outbound port
                         ^
                         |
                  outbound adapter
```

The domain must not import application or adapters. Application code may depend on domain types and protocols declared in the application layer. Adapters may depend inward on both.

## Inbound side

The CLI maps arguments and configuration into application commands and services. It is also the primary composition root for repositories, converters, gateways, renderers, and runtime managers. MCP maps protocol requests into the transport-neutral `ClauseProvider` and `McpClauseService` boundary. Neither adapter owns business rules.

## Outbound ports

The application layer defines repositories and capabilities for, among other concerns:

- engineering documents and stage artifacts;
- extracted and normalized documents;
- alignment and review artifacts;
- construction contracts;
- prompt, dataset, corpus, annotation, and run persistence;
- document conversion and rendering;
- LLM completion;
- command execution and runtime health.

The formal-semantic boundary follows the same rule. `FormalSemanticProjector`, `FormalSemanticProjectionRepository`, and `FormalSemanticSerializer` expose provider-neutral application needs. Slice 3 provides a deterministic application projector, a versioned filesystem projection repository, and a Turtle serializer in `adapters/rdf`; SPARQL engines, graph stores, and GraphRAG-style retrieval implementations remain optional adapters and must not leak their APIs into the domain model.

Ports should express application needs rather than mirror third-party APIs. The formula-visual adapter is deliberately narrow: it consumes adapter-neutral page/bounding-box evidence and does not perform formula discovery or semantic recognition.

## Adapter ownership

| Adapter package | External concern |
|---|---|
| `adapters/docling` | Primary PDF extraction, Docling contract validation, and composition with source-backed formula visuals |
| `adapters/pdf` | Deterministic source-PDF region rendering for already identified formula items |
| `adapters/filesystem` | Persistent application repositories |
| `adapters/atlasdata` | AtlasData import, lifecycle, and round-trip output |
| `adapters/markdown` | Document and review rendering |
| `adapters/doorstop` | Doorstop hierarchy and publication templates |
| `adapters/llm` | Codex CLI, OpenAI-compatible APIs, RamaLama process control |
| `adapters/mcp` | MCP protocol, HTTP security, process management, audit |
| `adapters/gemara` | Gemara GuidanceCatalog/ControlCatalog projections, IDs, mappings, and traceability |
| `adapters/governance` | Use-case candidate analysis and Gemara Policy scaffold projection |
| `adapters/complytime` | Governance bundles, ComplyPack authoring/CLI boundary, EvaluationLog feedback |

## Migration state

ADR 0001 establishes the current architectural dependency direction. Canonical implementations live in focused packages such as `application/workflow`, `application/normalization`, `application/evaluation`, and `application/semantic_qualification`. During the active refactoring there is no requirement to retain compatibility exports below `application/services`; obsolete exports should be removed when their callers are migrated. New code must import canonical packages and must not add concrete-adapter dependencies to reusable application services.

Architecture tests enforce the dependency direction across the complete active package tree. They parse imports statically, including relative imports, and reject:

- `domain/**` dependencies on application, adapters, or CLI;
- `application/**` dependencies on concrete adapters or CLI;
- direct domain/application imports of concrete graph, document, publication, and AI frameworks that belong behind adapters;
- generic `application/evaluation` dependencies on standards-specific semantic qualification; and
- structural-taxonomy dependencies on semantic-classification resources or services.

Unit tests construct application services with test doubles; integration tests verify real adapter contracts and composition roots. A new capability boundary that must remain independently replaceable should normally gain an architecture guard when it is introduced.

### Structured table retrieval

T4 exposes `RetrievalTokenizer` and `RetrievalProjectionWriter` as provider-neutral outbound
ports. `TableRetrievalProjectionService` creates deterministic table, row, concept, and relation
retrieval documents with the `structured-table-v1` tokenization profile. Concrete tokenizer,
embedding, vector-store, graph, or GraphRAG implementations remain adapters and must not become
part of the table domain model or T1-T3 knowledge contracts.

### Governance adapter boundary

Governance Selection Profiles and candidate-decision types are domain concepts and have no Gemara
dependency. Gemara serialization and policy scaffolding remain outer adapters. Likewise,
ComplyTime and ComplyPack are downstream integration concerns: reusable application/domain code
must not import their concrete APIs.

The integration deliberately preserves the direction:

```text
canonical document + governance profile
        -> adapter projection
        -> Gemara / ComplyTime / ComplyPack
```

EvaluationLog import resolves external result identities through generated traceability and emits a
separate feedback projection; it does not mutate the canonical document.
