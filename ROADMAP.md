# Roadmap
- Correct representative corpus eligibility by excluding clauses without normalized content, separating content from structural context, hashing content only, and recording duplicate-content and eligible-population statistics.

Standards Atlas is a deterministic engineering platform for analysing, maintaining, evaluating, and publishing relationships between international technical standards, specifications, and other engineering documents.

The current programme replaces the former IntelliDoc implementation with a maintainable architecture while restoring and extending its cross-standard engineering capabilities.

## Long-term vision

Standards Atlas shall become the reference platform for analysing relationships between standards from different standardisation domains. Functional Safety is the first knowledge domain, followed by Cybersecurity, Railway Interoperability, and further engineering domains.

## Version 0.7 — Deterministic document and evaluation foundation

Status: **completed through 0.7.1**

### Document pipeline

- Docling extraction and private source persistence.
- Deterministic normalized-document contract.
- Reference detection, alignment, review, and manual overrides.
- Canonical `EngineeringDocument` construction.
- Transformation ledger and end-to-end lineage.
- Golden corpus and layered qualification framework.

### Workspace and publication

- Separation of `.atlas` internal artefacts and `local` protected/user-facing data.
- Catalog-driven single-part and multipart workflows.
- Functional Safety publication hierarchy.
- Markdown and Doorstop publication with packaged templates.
- Reproducible workflow derivation reports.

### Semantic evaluation framework

- Generic clause-access services independent of transport protocols.
- Deterministic filtering, search, and balanced sampling.
- Local annotation-ready corpus construction.
- Versioned prompt/model benchmark manifests.
- Content-safe benchmark summaries and manifest fingerprints.

### MCP evaluation server

- Read-only MCP adapter over the evaluation services.
- stdio and Streamable HTTP transports.
- Bearer authentication, host/origin policy, DNS-rebinding protection, request limits, and audit logging.
- Container deployment examples.
- Independent compatibility probe and CI-ready smoke test.

## Version 0.8 — Restore and improve IntelliDoc relationship analysis

### 5.4 Gold-dataset management

- Define task-specific gold-dataset schemas.
- Add annotation, review, acceptance, and supersession states.
- Validate references to corpus clauses and normalized clause hashes.
- Support reviewer disagreement and adjudication.
- Preserve dataset lineage across revisions.

### 5.5 Benchmark and confidence framework

- Calculate precision, recall, F1, and task-specific metrics.
- Compare prompt and model versions against accepted gold datasets.
- Add confidence calibration and threshold analysis.
- Classify false positives, false negatives, and malformed outputs.
- Generate protected local detail reports and shareable aggregate reports.
- Establish regression gates for selected production configurations.

### 5.6 Relationship discovery

Restore the central IntelliDoc capability on top of the new architecture.

Detect and review:

- normative and informative references;
- adapted or inherited clauses;
- equivalent and overlapping concepts;
- terminology mappings;
- specialisation and constraint relationships;
- potential conflicts and gaps.

Support:

- one-to-one, one-to-many, and many-to-one relationships;
- partial clause mappings;
- model confidence and evidence;
- deterministic candidate persistence;
- human review and override workflows;
- relationship regression datasets.

### Knowledge Domain graph

Represent standards and relationships as an explicit graph rather than only as a publication tree. Initial relationship types include:

- `references`;
- `derives_from`;
- `adapts`;
- `specialises`;
- `constrains`;
- `equivalent_to`;
- `conflicts_with`;
- `supersedes`.

## Version 0.9 — Engineering analysis

Generate engineering artefacts directly from the Knowledge Domain:

- impact and dependency analysis;
- missing-mapping and coverage reports;
- consistency and terminology comparison;
- change propagation;
- graph exports and exploration;
- AI-assisted review based on traceable relationship evidence.

## Version 1.0 — Functional Safety Atlas

The first production-ready platform for analysing relationships between Functional Safety standards, with:

- deterministic document processing;
- qualified semantic evaluation;
- reviewed cross-standard relationships;
- complete navigation and engineering reports;
- durable qualification evidence;
- stable APIs and CLI;
- secured MCP access for engineering assistants.

## Beyond Functional Safety

### Cybersecurity

Examples include IEC 62443, ISO/SAE 21434, and the ISO/IEC 27000 family.

### Railway interoperability and operations

Examples include TSI, CCS, ERA guidance, and operational rules.

### Systems engineering

Examples include IEC 81346, ISO 15288, and SysML-based artefacts.

## Research topics

- semantic document comparison;
- model-assisted relationship discovery;
- confidence calibration for engineering decisions;
- automated impact prediction;
- knowledge-graph visualisation;
- engineering assistants with protected local context;
- configurable and qualifiable publication pipelines.


### Slice 5.3.7 - Codex integration — completed

- secure Streamable HTTP registration for Codex;
- environment-backed bearer authentication;
- explicit read-only tool allow list;
- reproducible configuration and verification workflow.

## Slice 5.4.3 — Baseline annotation proposals

Completed: versioned semantic-role task and prompt resources, provider-independent proposal orchestration, Codex and RamaLama adapters, durable request/response evidence, schema validation, proposal provenance, and resumable generation.

## Slice 5.4.4 — Human review workflow

Completed: local Markdown review export with embedded review data, validated import into canonical reviewed annotations, conflict and plausibility checks, and controlled publication from `local` to `data`.

### Slice 5.4.4a – Clause Reference Extraction and Resolution

Implemented: deterministic same-document clause and range detection, target resolution,
unresolved diagnostics, local persistence, CLI automation, and HITL context integration.
