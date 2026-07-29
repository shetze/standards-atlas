# Changelog


- Preserve raw provider output for failed structured generations in `response.txt`
  and `response.json`, record response previews and `finish_reason` in
  `failure.json`, tolerate Markdown-fenced JSON, classify truncated output, and
  raise the default semantic proposal output budget from 256 to 512 tokens.

- Improve semantic proposal progress diagnostics by reporting document key, clause reference, title, internal clause ID, retry attempts, elapsed time, and compact failure causes before and after long-running provider calls.
### Slice 5.3.7 - Codex integration

### Managed MCP dependency for Codex evaluation

- Start the configured MCP HTTP server automatically before Codex annotation proposals.
- Reuse an already running MCP server without taking ownership of it.
- Stop only a server started by the current Codex command.
- Add `--mcp-config`, `--mcp-autostart`, and `--mcp-autostop` controls.

- add a token-free Codex Streamable HTTP MCP configuration generator;
- restrict Codex to the qualified read-only Standards Atlas tool set;
- add safe Codex registration and verification scripts;
- add example project/user configuration and unit tests;
- document client setup, trust boundaries, and ADR 0043.

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog, and the project follows Semantic Versioning.

## Unreleased

### Changed

- Qualification-matrix models may override the global `repetitions` default.

### Changed

- Split qualification-matrix reruns into explicit `--resume`, `--overwrite`, and
  `--recompute` modes. Resume remains the default, overwrite regenerates proposals,
  and recompute rebuilds derived qualification and consensus artifacts without starting
  an LLM provider.

### Added

- Managed MCP HTTP server lifecycle through `mcp start`, `mcp status`, and `mcp stop`,
  including detached process execution, PID cleanup, endpoint monitoring, and persistent logs.

### Fixed

- Normalize otherwise valid semantic-role responses when `primary_role` is omitted
  from `semantic_roles`; retain the primary role by inserting it into the role set
  before strict schema and domain validation.

- Continue qualification-matrix execution after clause-level proposal failures; failed clauses remain available as diagnostics and reduce coverage instead of aborting the complete benchmark.

### Fixed

- make `evaluation qualification-matrix` execute the complete mandatory model/prompt/repetition matrix before qualification instead of only aggregating predeclared observations; retain the previous behavior behind `--aggregate-only`.
- map qualification prompt identifiers to their concrete prompt resource versions and keep optional reasoning runs opt-in through `--include-optional-reasoning`.

### Planned

- Gold-dataset lifecycle and annotation review.
- Precision, recall, F1, confidence, and error-classification reports.
- Cross-standard relationship discovery and review workflows.

## [0.7.1] - 2026-07

### Added

- Add deterministic same-document clause reference extraction and range resolution, local reference-analysis persistence, CLI support, and HITL review context integration.

- Add the Slice 5.4.4 human review workflow for semantic annotation proposals.
- Export proposal runs as editable local Markdown with embedded, validated review YAML.
- Import accepted, corrected, rejected, and ambiguous decisions as canonical reviewed annotations.
- Publish reviewed annotations and corpus manifests from `local` to content-safe `data`.
- Add ADR 0048 and a semantic annotation review user guide.

#### Semantic evaluation framework

- Generic, transport-independent clause-access services.
- Read-only filesystem-backed `ClauseProvider` implementation.
- Deterministic clause filtering, search, and balanced sampling.
- Reproducible local corpus construction with source-hash manifests.
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

- Fix Codex structured-output compatibility for semantic role proposals by removing
  the unsupported `uniqueItems` keyword from provider-facing JSON schemas. Duplicate
  semantic roles remain rejected by the local annotation contract.

### Changed

- Separate model-generated semantic evaluation candidates from the annotation workspace.
- Scope resumable proposal runs by corpus, prompt, provider, and model.
- Persist each candidate as `evaluation.yaml` beside its request and raw response.
- Ensure proposals generated by one model never cause another model's run to be skipped.

### Fixed

- Bound semantic proposal output to 256 tokens by default to prevent local models from hanging in schema-constrained generation.
- Classify request timeouts separately from temporary endpoint unavailability and avoid repeating deterministic 120-second timeouts unless `--retry-timeouts` is requested.
- Persist per-clause `failure.json` diagnostics with clause identity, error category, elapsed time, request fingerprint, prompt size and output-token limit.

### Slice 5.4.5 - Annotation resolution and metrics

- resolve semantic annotation evidence with `data > local > structure` priority;
- separate Gold, Silver, and Structure Agreement metrics;
- report exact match, primary-role accuracy, micro/macro precision, recall, and F1;
- add primary-role confusion matrices and confidence calibration metrics;
- report corpus coverage, stale diagnostics, knowledge-domain, and stratum slices;
- add machine-readable JSON and reviewer-friendly Markdown qualification reports;
- add the `evaluation annotations-metrics` CLI command and ADR 0049.

### Slice 5.4.6 - Model/prompt qualification matrix

- add a versioned shortlist contract with exactly four prompt variants and repeated runs;
- aggregate Gold, Silver, Structure, coverage, stability, latency, and memory results;
- calculate a Pareto front across quality, variation, runtime, and resource demand;
- enforce absolute and baseline-relative regression thresholds with CI-compatible exit codes;
- generate machine-readable JSON and human-readable Markdown comparison reports;
- add the `evaluation qualification-matrix` CLI command, example manifest, tests, and ADR 0050.

- Populate the example semantic-role qualification matrix with a realistic local
  shortlist: Granite 3.3 8B, Qwen3 14B, Gemma 4 12B, and Mistral Small 3.2 24B.
- Add optional reasoning modes as a third qualification dimension. Direct runs
  remain mandatory; missing reasoning-enabled runs do not fail qualification.

- Refine Slice 5.4.6 qualification shortlist and reliability gates: replace Granite with Qwen3 32B, correct Gemma 3 naming, add bounded-reasoning prompt, prompt-specific output limits, and explicit success/JSON/truncation metrics.

- Add a manifest-driven semantic-evaluation workflow with explicit reference, proposal,
  review, publication, metrics, and qualification stages.
- Add resumable evaluation workflow state markers, human-review gates, and auditable run
  reports under `.atlas/evaluation-workflow/`.

### Changed

- Replaced the duplicate semantic-evaluation workflow manifest with orchestration in the existing qualification-matrix manifest.
- Extended qualification matrices with optional reviewed-annotation imports and model-level consensus analysis.
- Added a fifth example model and a text-focused consensus configuration to `examples/evaluation/qualification-matrix.yaml`.
- Generate a Golden Corpus proposal and a focused HITL review queue after matrix execution.
- Aggregate repetitions before cross-model comparison so every model contributes one vote per clause.

### Fixed

- Allow qualification matrices to declare optional review imports so a fresh corpus can be evaluated before any HITL review exists.
- Correct manifest-relative paths in the qualification-matrix example for runs, corpora, and consensus outputs.
