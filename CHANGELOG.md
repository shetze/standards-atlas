## 0.8.1

### Changed
- Completed the modular refactoring of the core architecture.
- Split CLI, qualification, proposal, normalization, alignment and Docling processing into cohesive modules.
- Introduced shared infrastructure for artifacts, hashing, formatting and reporting.

### Notes
- This release is intended to preserve functional behaviour while significantly improving maintainability and extensibility.

- Add formula transcription enrichment with MCP discovery/read/submit tools, provenance-bearing LaTeX artifacts, explicit write capability gating, and deterministic application to preserved `FormulaBlock` values.

## Unreleased

- Visual-only formulas no longer propagate Docling pseudo-expressions into EngineeringDocuments or Markdown; the preserved PNG and `semantic transcription unavailable` caption remain the authoritative fallback.

- Archive completed qualification executions as immutable `qualification-run-NNN.zip` evidence under `local/evaluation/`, with embedded run metadata and a compact `qualification-run-index.json` instead of encoding matrix/tool versions in long archive filenames.

- Fix qualification workflow execution so a completed matrix with a failing
  qualification result remains a valid workflow outcome while direct matrix
  invocations can still use exit status 1 as a CI quality gate.

- Add a typed workflow manifest envelope and consolidate workflow inputs under repeatable/comma-separated `--manifests`.

- Unify workflow orchestration under `workflow plan` and `workflow run` with `--task documents|qualification`; qualification composes Markdown publication, corpus build, and matrix evaluation while excluding Doorstop publication.
- Replace the workflow `--catalog` option with `--manifest` and move the canonical standards definition to `manifests/standards.yaml`.
- Move the canonical qualification matrix manifest to `manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml` and expose it as `--qualification-manifest`.

### Changed

- Persist negative Knowledge Kind decisions with decision confidence instead of positive-label confidence.
- Align effective cascade statement-function finalization with the downstream review acceptance threshold.
- Distinguish observed from unresolved structural-applicability conflicts so resolved conflicts remain auditable without forcing stale HITL review.
- Record clause-level cascade entry/exit provenance and per-stage dimension-resolution deltas.

### Added

- Generate `qualification-analysis-metrics.json` and a versioned qualification-analysis ZIP with report, configuration, cascade, provenance, and SHA-256 manifest data at the end of consensus-enabled matrix runs.
- ADR 0056 documents qualification cascade provenance and policy coherence.

### Changed

- Make semantic consensus dimension-aware: unanimous `none` decisions now carry decision
  confidence, cascade resolver decisions remain authoritative in final aggregation, scope
  context is governed by applicability, and structural-prior/applicability conflicts are
  surfaced for escalation or HITL review.
- Report per-dimension consensus categories, decision confidence, overall resolution status,
  and cascade resolution sources.

### Added

- Preserve Docling-identified `visual_only` formulas as source-derived PNG assets using a
  dedicated PyMuPDF adapter and existing page/bounding-box evidence.
- Propagate formula visual assets through normalized documents, `FormulaBlock`, and
  Markdown publication.
- ADR 0055 defines the separation between deterministic visual preservation and later
  semantic formula transcription.

## 0.8.0 - 2026-08-05

### Added

- Addressable `KnowledgeTable` and `KnowledgeRecord` projections derived from structured table blocks.
- Stable table and row identifiers with cell-level structure and source evidence.
- IEC 61508-3 recommendation-matrix interpretation with normalized SIL recommendations,
  cross-references, and alternative groups.
- Portable table ontology for work-product, responsibility, verification, traceability,
  and applicability matrices.
- Read-only MCP operations for listing and retrieving knowledge tables and records.
- Central semantic-task eligibility policy with alternative-task routing for
  table-dominant content.

### Changed

- Statement-function corpora exclude table-dominant clauses by default and record the
  exclusion reason in corpus and proposal-run evidence.
- Mixed narrative/table clauses are classified only by their narrative statement
  function; table-derived relations are not projected back onto clause labels.
- The architecture now distinguishes clause semantics from table semantics while
  retaining `EngineeringDocument` and structured clause content as the canonical source.


### Changed

- Define compatibility, migration, regeneration, deprecation, and release policies for maintained contracts.
- Extend security documentation with assets, actors, trust boundaries, threats, and mandatory controls.
- Define the staged target architecture for reviewed cross-domain relationship mapping.
- Establish documentation lifecycle, ownership, review-trigger, and removal rules.
- Consolidate the catalog format and getting-started documentation into one canonical reference each.
- Archive the semantic-model next-steps document as historical rationale after ADR 0050 and ADR 0051 implementation.
- Mark superseded ADR provisions explicitly and update the Knowledge Domain architecture description.
- Split the CLI composition root into focused command modules.
- Separate generic evaluation from semantic qualification services.
- Split workflow planning, execution, and recovery responsibilities.
- Express document normalization as an ordered transformation pipeline.

- Extract named methods and techniques during normalization into a provenance-preserving document index and a separate `methods-and-techniques.json` artifact for future MCP/skill integration.
- Include readable clause references, titles and normalized clause text in consensus review
  documents so HITL decisions can be made without looking up clauses externally.
- Preserve the same clause context in consensus reports and golden-corpus proposals.
- Resolve review context from existing corpus datasets during qualification-matrix recomputation.

### Added

- `workflow run --overwrite --keep <stage>` for regenerating downstream derived artifacts while reusing selected existing stages such as Docling conversion output.


### Added
- Multi-dimensional `StructuralProfile` replaced legacy semantic roles.
- Internal cross-clause references are resolved during Markdown export and rendered as links when target clauses are available.
- Domain-aware structural taxonomy with normative/informative inheritance.
- Background MCP/LLM lifecycle management improvements and qualification-matrix reliability fixes.
