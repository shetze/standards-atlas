## 0.8.1
- Relax knowledge-primary cascade resolution to a 0.60 majority threshold across all stages while keeping secondary knowledge-set disagreement diagnostic-only.
- Qualification now treats primary knowledge-kind agreement separately from full multi-label knowledge-set agreement. Primary disagreement/confidence can drive cascade escalation, while secondary-set disagreement remains diagnostic-only.
- Split applicability qualification into explicit `applicability_present` presence and optional subtype classification while preserving legacy inference for older task payloads.
- Refine applicability qualification prompts around an explicit applicability-question test and distinguish activity conditions from conditions on normative applicability.
- Tightened current role qualification prompts with explicit actor/non-actor, passive-without-actor, target, relation-class priority, and applicability-leakage boundaries.


### Formal Semantic & Context Model — Slice 3

- add deterministic ABox/CBox projection from canonical `EngineeringDocument` data
- project Knowledge Domain, semantic taxonomy, applicability, normative, structural and lineage context into clause CBox frames
- preserve document containment, parent/sibling structure and resolved semantic relations as ABox assertions
- add Standards Atlas Core and Functional Safety ontology 1.1.0 resources for projection/reification vocabulary
- add provider-neutral semantic serialization port and deterministic Turtle RDF adapter
- add versioned filesystem persistence for rebuildable formal-semantic projections
- keep protected clause body text and RDF/graph-provider dependencies outside the formal projection domain contract

### Role qualification tuple consensus

- split role qualification into explicit role-semantics presence and structured relation-tuple consensus
- add deterministic role-candidate diagnostics for sparse-negative hard cases
- add semantic-profile task 2.3.0 and v5 prompts without a required primary role-relation label


### Changed
- Completed the modular refactoring of the core architecture.
- Split CLI, qualification, proposal, normalization, alignment and Docling processing into cohesive modules.
- Introduced shared infrastructure for artifacts, hashing, formatting and reporting.

### Notes
- This release is intended to preserve functional behaviour while significantly improving maintainability and extensibility.

- Add formula transcription enrichment with MCP discovery/read/submit tools, provenance-bearing LaTeX artifacts, explicit write capability gating, and deterministic application to preserved `FormulaBlock` values.

## 0.8.3 - 2026-08-20

- carry materialized structural taxonomy context, reference mentions, and scope edges into qualification corpus items and LLM requests
- archive exact corpus, task, prompt, and ontology inputs in immutable qualification-run evidence packages
- bump qualification-run archive and metadata schema to 1.2
- improve qualification reproducibility before fresh matrix runs
- materialize AtlasData clause hierarchy into canonical `Clause.parent_id` values so structural taxonomy emits real nodes, ancestors, and local sibling sequences


## Unreleased

### Formal Semantic & Context Model — Slice 4

- add ontology-guided engineering concept and local relation extraction behind a provider-neutral application port
- use existing Knowledge Domain and semantic taxonomy results as deterministic extraction eligibility signals
- persist rebuildable semantic extraction artifacts separately from canonical EngineeringDocuments
- constrain LLM extraction to classes and properties declared by selected formal OWL ontologies
- reject cross-domain equivalence/mapping assertions during extraction
- augment ABox/CBox projections with inferred entities, relations, confidence, and extraction provenance
- extend the current core ontology vocabulary in place for Slice-4 epistemic context facets


- Harden multidimensional qualification against duplicate set-like labels: compact prompts require unique values and proposal normalization deduplicates statement, knowledge, process, and applicability labels before strict validation.

- Align the semantic qualification contract with the open RoleRelation model: remove legacy scalar role-relation labels from task/prompt schemas, require `relation_class` plus evidence-grounded `predicate`, preserve archived-run read compatibility, and base new role-relation confidence on structured tuple evidence.

- Refine role golden-corpus review sampling: exclude aggregate multipart-standard documents when part documents are available, emit fully qualified part references for HITL review, and move internal clause identifiers and hashes to the end of the review CSV.

- Separate applicability-presence and applicability-subtype cascade resolution, skip subtype escalation when applicability is absent, preserve legacy manifest behavior, and report applicability escalations that remain unresolved after each stage.

- Finalize the taxonomy/ontology split: remove the legacy deterministic `SemanticClassifier`, keep `ENRICH` classification-free, make AtlasData onboarding structure-only, and enforce `TAXONOMY -> ONTOLOGY` ownership with architecture tests and updated UML diagrams.

- Add bounded schema-reader compatibility with visible deprecation warnings, current-only writers, and an explicit temporary four-version major-transition window.

- Establish a clean schema compatibility baseline: persistent contracts declare current schema versions explicitly, legacy EngineeringDocument readers are removed, and cache/work formats are excluded from compatibility guarantees.

- Separate semantic taxonomies from semantic tasks; introduce independently versioned statement, knowledge, process, applicability, and responsibility taxonomies and make `semantic-profile-classification` the canonical multidimensional 2.x task while retaining the previous name as a compatibility alias.
- Add a modular deterministic structural-taxonomy engine with versioned classifier registry and YAML contract validation; move ISO/IEC document categorization out of the AtlasData adapter.
- Introduce lifecycle-based generated storage: persistent machine state in `.atlas/data`, disposable caches in `.atlas/cache`, retained workflow scratch state in `.atlas/work`, and all HITL artifacts below `local/review`.
- Add `standards-atlas clean`; workflow scratch state is cleared before a new workflow run while human-facing `local/` artifacts are never removed.
- Move LLM and MCP runtime state into `.atlas/work`, LLM response caches into `.atlas/cache`, and add a migration script for legacy workspace layouts.

- Add optional read-only LLM normalization-quality qualification with reusable corpus input, model comparison, and JSON/JSONL/Markdown reports.

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

### Role-model Slice 4

- Added a focused, reproducible role golden-corpus builder with seven sampling strata.
- Added a reviewable `role-golden-corpus.yaml` contract that separates proposed from published gold cases.
- Added presence and complete actor-relation-target tuple regression metrics against published gold.
- Added `evaluation role-corpus-build` and `evaluation role-corpus-evaluate` commands.
- Added the `role-relation-golden-corpus-v1.yaml` 140-case sampling profile.
- Extended consensus golden proposals with role-semantics presence, candidate markers, and tuple consensus.

### Slice 3b — applicability semantic boundary

- narrow applicability qualification to explicit applicability assertions
- separate applicability from structural scope, prerequisites, assumptions, and local conditions
- add applicability-functions ontology 1.2.0 and semantic-profile task 2.4.0
- add v6 qualification prompts with positive and negative applicability boundary examples
- centralize deterministic applicability detection for structural priors and diagnostics
- add a v5 applicability-semantics qualification manifest while retaining the v4 baseline

### Slice 3c — applicability presence model eligibility

- exclude GLM-4 9B and SmolLM3 3B from applicability-presence consensus after Slice 3b calibration analysis
- preserve their participation in other semantic dimensions and keep subtype eligibility independent
- validate cumulative dimension-eligible voter counts for filtered cascade configurations
- expose a manifest helper for inspecting model ids eligible for each applicability dimension

### Role relation open-class review model

- replace the closed role-relation enum in structured extraction with open `relation_class` plus evidence-grounded `predicate`
- define the recommended core classes `performance`, `responsibility`, `assignment`, `dependency`, `consultation`, `information`, `participation`, and `membership`
- keep legacy relation values readable by mapping them into the new structure
- update role tuple consensus and golden regression to compare actor, relation class, predicate, target, and condition
- make review `category` editable and allow `none` as reviewed ground truth
- generate a role-review guide beside the CSV and update the HITL publish workflow for the new columns

### Simplified role relation qualification contract

- reduce `RoleRelation` to `actor`, open `relation_class`, and `target` for ontology/RACI classification
- remove predicate, condition, evidence, and per-relation confidence from the active role contract
- present role presence and role relations as one role-semantics dimension in qualification prompts
- replace confusing process-model role terminology with process-model functions
- move role qualification rules before the final JSON output contract and place JSON output last
- update role golden review and tuple consensus to the simplified actor-class-target structure

- Refine applicability presence guidance to distinguish normative applicability from operational conditions and method-selection conditions.

### Applicability presence golden qualification

- Exclude Granite from `applicability_presence` voting while retaining it for other dimensions.
- Add a dimension-specific minimum presence-voter count so filtered presence voting does not weaken other qualification dimensions.
- Add a small run-derived applicability golden-review workflow for presence hard cases, including per-model accuracy metrics to support evidence-based model eligibility.

- Integrated ontology-guided semantic extraction as an explicit qualification-run step with ontology-conformance, confidence, and optional gold metrics.
