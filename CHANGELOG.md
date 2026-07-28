# Changelog
- Correct representative corpus eligibility by excluding clauses without normalized content, separating content from structural context, hashing content only, and recording duplicate-content and eligible-population statistics.

### Slice 5.4.1 - Corpus and annotation contract

- define content-safe corpus manifests and clause annotation YAML contracts;
- identify annotations by knowledge domain, document key, and clause id;
- add normalized clause hashes for integrity and staleness detection;
- preserve generated proposals separately from reviewed semantic-role annotations;
- implement proposed, reviewed, and published lifecycle states;
- resolve published `data` annotations before local reviewed or proposed variants;
- publish reviewed local annotations as Git-trackable reference data;
- document the decision in ADR 0044.

### Slice 5.3.7 - Codex integration

- add a token-free Codex Streamable HTTP MCP configuration generator;
- restrict Codex to the qualified read-only Standards Atlas tool set;
- add safe Codex registration and verification scripts;
- add example project/user configuration and unit tests;
- document client setup, trust boundaries, and ADR 0043.

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog, and the project follows Semantic Versioning.

## Unreleased

### Planned

- Gold-dataset lifecycle and annotation review.
- Precision, recall, F1, confidence, and error-classification reports.
- Cross-standard relationship discovery and review workflows.

## [0.7.1] - 2026-07

### Added

#### Semantic evaluation framework

- Generic, transport-independent clause-access services.
- Read-only filesystem-backed `ClauseProvider` implementation.
- Deterministic clause filtering, search, and balanced sampling.
- Reproducible local corpus construction with clause-hash manifests.
- Versioned prompt/model benchmark matrices.
- Content-safe matrix reports that omit clauses and model responses by default.

#### MCP server

- `standards-atlas mcp serve` with stdio and Streamable HTTP transports.
- Read-only tools for standards and clause discovery, retrieval, search, and sampling.
- MCP resources for document and clause access.
- Bearer-token authentication for remote operation.
- Configurable host and origin allow-lists with DNS-rebinding protection.
- Request-body limits and content-safe JSONL audit logging.
- Containerfile, Compose configuration, and remote deployment example.

#### MCP compatibility qualification

- Independent Streamable HTTP reference client.
- `standards-atlas mcp probe` command.
- Reproducible `tools/mcp/smoke.sh` end-to-end check.
- Protocol negotiation, required-tool, real tool-call, and resource checks.
- Machine-readable compatibility reports suitable for CI evidence and SDK upgrades.

#### Architecture documentation

- ADR 0040 for transport-independent evaluation services and the MCP inbound adapter.
- ADR 0041 for local protected evaluation data and content-safe reports.
- ADR 0042 for secure and qualified Streamable HTTP deployments.

### Changed

- Project version increased to 0.7.1.
- Normalizer implementation version is decoupled from the package release version so patch releases do not invalidate unchanged golden artefacts.
- Unknown MCP HTTP configuration fields are rejected instead of being silently ignored.
- Golden-corpus comparison uses the normalized JSON data model rather than serialization details.

### Fixed
- Exclude duplicate clause occurrences contributed by composed multipart family documents from semantic corpora and render content-duplicate groups with readable clause references and titles.

- MCP SDK compatibility for request-size enforcement.
- Ruff-compliant optional MCP test setup.
- LAN access failing with `421 Invalid Host header` despite configured allow-lists.
- Origin wildcard handling for explicit port patterns.
- Golden-corpus regressions caused solely by package-version changes.

## [0.7.0] - 2026-07

### Added

#### Verification and qualification framework

- ADR 0039 and a layered testing strategy for unit, contract, property, integration, workflow, and qualification tests.
- Reusable filesystem repository contract tests and Hypothesis-based persistence properties.
- `standards-atlas qualification golden-corpus` with auditable JSON and Markdown reports.
- Explicit pytest markers for contract, property, and qualification test classes.

#### Workspace and publication architecture

- Separation between internal workflow artefacts (`.atlas`) and local user data (`local`).
- Local source-document repositories and dedicated Markdown and Doorstop export locations.
- Explicit publication hierarchies, initially for Functional Safety.
- Hierarchy-aware Doorstop publication with packaged templates.

#### Deterministic workflow

- Catalog-driven workflow planning and execution.
- Human review gates for alignment decisions.
- Completion reports with plans, commands, reused and generated artefacts, hashes, software versions, Git revision, and timestamps.

#### Documentation

- Reorganised architecture, user, development, and reference documentation.
- Draw.io-based architecture diagrams.
- ADRs for multipart standards, workspace architecture, publication hierarchies, workflow derivation reports, and packaged Doorstop templates.

### Changed

- Completed the migration to the staged document pipeline:

```text
PDF
  -> Docling
  -> ExtractedDocument
  -> NormalizedDocument
  -> Reference Detection
  -> Alignment
  -> EngineeringDocument
  -> Content Blocks
  -> Exports
```

- Markdown export now originates from canonical `EngineeringDocument` objects.
- Doorstop export operates on publication hierarchies rather than individual documents.

### Fixed

- Multipart and annex handling.
- Deterministic document composition and hierarchy generation.
- Recovery of incomplete Docling persistence.
- Golden-corpus stability and workflow reproducibility.

## [0.6.x]

Development snapshots leading to the new architecture. No stable release.
