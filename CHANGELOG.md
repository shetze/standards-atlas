## 0.8.1

### Changed
- Completed the modular refactoring of the core architecture.
- Split CLI, qualification, proposal, normalization, alignment and Docling processing into cohesive modules.
- Introduced shared infrastructure for artifacts, hashing, formatting and reporting.

### Notes
- This release is intended to preserve functional behaviour while significantly improving maintainability and extensibility.

- Add formula transcription enrichment with MCP discovery/read/submit tools, provenance-bearing LaTeX artifacts, explicit write capability gating, and deterministic application to preserved `FormulaBlock` values.

## Unreleased

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
