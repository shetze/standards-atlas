# Changelog

This changelog summarizes the architectural refactoring of Standards Atlas. It intentionally consolidates the detailed Git history into a compact record of the major design transitions and externally relevant capabilities. Individual fixes, test-only changes, data corrections, and intermediate refactoring commits are represented by the milestone in which they became part of the architecture.

## Unreleased — Bounded context-enrichment baseline fixes (2026-09-10)

- Add source-bound, allowlisted external single-target ID completion to the existing
  model-free repair command. Preserve all other canonical values, protected routing,
  provenance and last-run outcomes; require a separate resolver report for writes.
- Diagnose unresolved targets by reason without replacing existing counters or
  equating whole-document/object addresses with failed inference.
- Exclude bare scientific-number reference matches, retain unchanged request input
  fingerprints, and stop non-recoverable context-window retries while recording the
  complete first-to-last failure chain and provider counters.
- Align repeated object range labels, separator commas after exact norm editions,
  and labelled multi-letter object coordinates. Keep object/clause namespaces,
  complete-group requirements and semantic scope safeguards unchanged.
- Add bounded-regression and CLI coverage, a 452-entry baseline allowlist, and
  offline qualification results. Do not replay rejected answers into canonical data.

## 0.8.7 — Enrichment publication and reference resolution (2026-09-09)

- Correct context-to-qualification runtime handoff with portable container inventory and exact
  host-port inspection; surface engine errors, reconcile reused/stale ownership and preserve the
  endpoint shutdown guard. Do not terminate foreign, ambiguous or other-port runtimes.
- Preserve primary qualification failures during cleanup and always release MCP resources; do not
  repeat a failed initial/model-switch stop from the finalizer.
- Add `--resume-after-context` for a checksum-verified continuation from a saved context baseline,
  including partial ones, without rerunning context or replacing the baseline archive/receipt.
  Reject changed canonical inputs, diagnostics, manifests and context configuration before inference.

- Default end-to-end enrichments to complete baseline collection despite individual invalid context
  responses; retain explicit `--fail-on-context-failure`, strict validation and technical/review gates.
- Record per-clause context outcomes, including failed attempts retaining older values. Revisit
  incomplete document checkpoints and retry their failed clauses without reloading rejected cache
  answers, while reusing successful and preserving protected values.
- Freeze private context and published baselines with aggregate diagnostics, exact code/configuration,
  canonical documents and checksums; include companions, referenced evidence and the qualification
  archive after publication. Never overwrite an earlier baseline or equate completion with approval.

- Separate standard identities from reference coordinates before detecting ranges; preserve true
  lists/ranges and expand shared coordinates across all explicitly named standard parts, with
  unchanged source spans and `reference-mention-extractor/v3` provenance.
- Apply a bounded, source-verified information-routing safeguard before canonical scope addressing
  and during model-free repair: retain reading-list/FAQ citations as references, not scope edges;
  neutralize unsupported informational roles, never reinterpret a genuinely governing statement.
- Record semantic corrections privately, reject mixed scope evidence through the existing retry
  gate, and report unresolved reference targets with evidence separately from scope targets.
  Refresh unconfirmed baseline references during standalone context enrichment as well as taxonomy.

- Recognize labelled figure/table citations consistently in extraction and scope resolution,
  including mixed lists, ranges and suffix-qualified targets. Never bind an object label to an
  equal-numbered clause or widen an unresolvable target to its document.
- Preserve complete valid citation groups with null target IDs when the TOC lacks an exact member,
  and report unresolved scope addresses separately from context generation failures. Keep the
  original classification during address resolution. Semantic corrections require separate
  source-grounded evidence and explicit private diagnostics.

- Separate the default `context-routing-v3` scope extraction contract from canonical ScopeReach:
  extract target citations plus descendant intent, then deterministically build document, part,
  clause and subtree reaches. Resolve complete part lists against physical documents and never
  null a meaningful citation to satisfy a mutually exclusive canonical field constraint.
- Include the target catalogue/structure in reuse fingerprints. Preserve strict domain/schema
  validation and the publication gate; record both rejected attempts in private per-document
  diagnostics, and supply rejected JSON to the corrective retry.

- Add explicit `--task enrichments`, composing document preparation, qualification, verified
  adoption, public/private transfer, reimport and CBox reporting through existing workflow APIs.
- Reuse native Docling artifacts by default; prepare all selected structures before context,
  preserve alignment gates and optionally stop on context-inference failures before publication.
- Qualify all eligible selected physical clauses by default, with isolated full/sample run roots
  and source-only corpus context that excludes accepted semantic output feedback.
- Handoff the exact immutable archive via a checksum- and matrix-verified receipt; reuse it only
  while run inputs and ZIP bytes remain current. Do not guess archive sequence numbers.
- Invoke the new composed task in-process without CLI subprocess glue; keep standalone documents,
  qualification and knowledge behavior and public schema/authority policies unchanged.
- Add synthetic two-document persistence/idempotence integration coverage and document usage.
- Make end-to-end `--fresh` refresh generated context routing as well as qualification, bypassing
  the context LLM cache while preserving confirmed routing. Retry schema-valid but semantically
  invalid routing responses once with a distinct corrective request and report residual failures.
- Validate every structured LLM response locally against its requested JSON Schema before caching;
  discard stale schema-invalid cache entries and encode scope-reach cross-field invariants directly
  in the context-routing-v2 schema so invalid reach combinations are rejected before domain merge.

## Unreleased — Presence-only public role semantics (2026-09-09)

- Publish only `enrichments.semantic.role_semantics_present` for the role-semantics dimension;
  temporarily omit role relations, relation types and their attribute fingerprints.
- Remove these deferred fields from existing selected companions during re-export, including
  retained clauses in partial updates, with explicit `omitted` dry-run/write diagnostics.
- Keep canonical role values, provenance, reviewed TOC tags and existing private evidence intact;
  preserve presence true/false/unknown and other published attributes without a schema change.
- Cover fresh and existing-companion exports, protected local details, private-store preservation
  and stable re-export after canonical empty dependents are regenerated on import.

## Unreleased — Source-grounded canonical reference repair (2026-09-09)

- Share an exact standard/part/edition-aware coordinate index between source reference extraction
  and context routing; support annexes, bare subclauses, bounded lists and same-level ranges.
- Refresh deterministic reference context before taxonomy and supply current source-grounded
  targets to context enrichment. The new default context-routing-v2 prompt interprets roles but
  leaves reference target IDs/titles to deterministic resolution.
- Validate explicit scope coordinates as well as reference targets before canonical persistence;
  retain verified structural scope edges without mistaking condition citations for scope targets.
- Recover already overwritten self/ancestor references only from unambiguous, verbatim source
  evidence; preserve original roles and evidence and flag ambiguous/unverified conflicts for review.
- Add model-free document repair-context-routing with dry-run diagnostics, exact-byte backups,
  explicit --write, confirmation protection and idempotent canonical repair before public export.
- Keep canonical schema 9, AtlasData enrichment schema 1.2 and evidence schema 1.0 unchanged.

## Unreleased — Explicit context-routing reference resolution (2026-09-09)

- Resolve local reference-routing text before accepting provider-supplied clause IDs. Distinguish
  genuine self references from explicit annex/subclause citations with incorrectly copied self IDs.
- Retain unresolved or ambiguous citation text with a null local target ID; never manufacture a
  self-link. Leave external targets untouched and keep short references within their source edition.
- Repair fresh and reused generated routing without changing evidence, roles or provenance; retain
  confirmed canonical routing protection and the existing ID-based scope-reach display repair.
- Normalize public routing and private values together on export. Keep enrichment schema 1.2 and
  regenerate affected generated companions from original canonical routing without new LLM calls.
- Cover conflicting annex IDs, genuine self references, missing/ambiguous/external targets, reuse,
  private hydration, existing-companion repair and byte-stable re-export with regression tests.

## Unreleased — Process-function qualification through AtlasData (2026-09-09)

- Preserve actually supplied process sets and primary labels through per-model votes,
  separate consensus decisions, stage/resolver snapshots, review and archive diagnostics.
- Distinguish observed empty/null from missing/unknown; collapse repetitions instead of
  counting them as independent votes. Recover old observations only from matching structured
  responses, never from rationale or default-filled legacy interviews.
- Add optional process-driven escalation without increasing existing manifest workloads.
- Adopt usable process decisions through the existing authority-aware canonical merge and
  AtlasData companion roundtrip. Invalidated stale primaries remain unknown, not false null votes.
- Write consensus schema 5.0 and golden proposal 4.0; preserve old consensus 4.0 policy hashes.
  Keep canonical schema 9, adoption 1.0 and archive layout 1.5 unchanged.
- Test fresh synthetic provider-to-AtlasData roundtrips and retained Run 074 compatibility.

## Unreleased — AtlasData enrichment schema 1.2 readability (2026-09-09)

- Add the exact legacy `atlasdata_md5` TOC identifier to every persisted clause and validate it
  against the owning AtlasData file instead of recomputing a reference hash.
- Emit clauses in physical document order and persist the internal heading text so reviewed
  AtlasData headings and normalized source headings can be compared directly.
- Centralize all SHA-256 state/provenance references under structured `fingerprints:` mappings;
  keep the AtlasData MD5 outside that block because it is a record identity, not a fingerprint.
- Omit redundant `availability: known` and duplicated generated path/availability fields while
  retaining explicit `availability: unknown`.
- Keep unresolved `ambiguous_candidates` as internal/WIP subject-identification state instead of
  publishing it as accepted AtlasData knowledge.
- Canonicalize local context-routing targets from resolved `clause_id` values so persisted scope
  reaches and reference routings always carry the actual target-clause reference.
- Schema 1.0/1.1 companions are intentionally unsupported; schema 1.2 is regenerated from canonical
  state rather than migrated in place.

## Unreleased — Effective CBox consumption and explicit knowledge workflows (2026-09-09)

- Share accepted canonical CBox values, attribute availability and provenance across corpus
  projection, Prompt Workbench and a private `document cbox-report` inspection command.
- Add an opt-in effective frame and explicit task-isolated frames; qualification always
  masks stored target labels, including alternate template variables and adaptive questions.
- Add the model-free `workflow --task knowledge` path for explicit adoption, public export,
  reimport and reporting. Optional restoration in document/qualification workflows precedes
  context enrichment and downstream consumers; default workflows do not publish knowledge.
- Validate live inputs for corpus/context/matrix checkpoints and proposal reuse; preserve
  renderer-independent semantic reuse while rejecting changed source/model/prompt inputs.
- Reuse restored context-routing results by their input identity without new gateway calls;
  retain confirmation protection and versioned existing persistence contracts.

## Unreleased — AtlasData knowledge roundtrip (2026-09-09)

- Added explicit `atlasdata export-enrichments` / `import-enrichments` with default dry-run,
  per-attribute reports, all-document preflight and atomic, byte-stable per-file writes.
- Persist selected canonical values in versioned, physical-document AtlasData companions.
  Preserve primary labels, presence-only/negative/unknown states, vote support, explicit
  confirmations and protected unattributed values without promoting generated hints to gold.
- Reuse manifest-owned structural imports and the canonical group-wise merge. Distinguish
  normalized-source and AtlasData heading hashes; reject stale identity, content or editions.
- Keep source-bearing context and original provenance in a private content-addressed store;
  export only bounded public views and references. Missing private values defer restoration,
  or fail preflight with `--strict-evidence`; protected source text is never reconstructed.
- Keep canonical schema 9 and reviewed TOC semantics unchanged. Automatic CBox/workflow
  consumption is provided by the subsequent slice above; process-function qualification
  remains separate.

## Unreleased — Canonical knowledge adoption (2026-09-08)

- Added `document adopt-qualification`: manifest-verified archive input, default dry-run,
  explicit canonical writes, per-attribute diffs, source checks, and idempotent replay;
  final Applicability policy decisions replace gate results without new model calls.
- Extended canonical schema to 9 for explicit primary labels, assessment availability,
  decision support, and authority-aware enrichment merging. Schema 8 remains readable;
  populated unmarked legacy values are protected without inventing authoritative status.
- Fixed Applicability tag reimport and added opt-in incremental `--merge` to
  `atlasdata apply-semantic-annotations`, retaining reviewed publication semantics.
- Qualification and adoption do not implicitly publish attributes. Public persistence is
  provided by the subsequent explicit AtlasData roundtrip commands above.

## 0.8.6 — Gemara and ComplyTime governance integration (2026-09-01)

### Governance interchange and executable-compliance hand-off

- Added deterministic Gemara `GuidanceCatalog` and `ControlCatalog` projections with stable IDs,
  semantic mapping, cross-layer links, and SHA-256-bound clause-level traceability.
- Added evaluator-independent ComplyTime governance source bundles and explicit ComplyPack authoring
  workspaces while keeping evaluator policy generation outside Standards Atlas.
- Added Governance Selection Profiles, deterministic `selected` / `excluded` / `undetermined`
  candidate analysis, and draft Gemara Policy scaffolding for use-case-specific selection without
  proliferating filtered catalog variants.
- Added Gemara `EvaluationLog` feedback import that resolves Control and Assessment Requirement
  results back to Standards Atlas clauses without mutating canonical EngineeringDocuments.
- Documented the end-to-end Gemara/ComplyTime architecture, CLI workflows, artifact contracts,
  policy-authoring boundary, OCI behavior, and feedback lineage.

## Unreleased — Refactoring consolidation (2026-08-20 to 2026-08-28)

### Semantic architecture and qualification

- Finalized the separation of **structural taxonomy**, **semantic classification**, and **formal ontology**. Deterministic structural context is materialized before LLM-assisted semantic processing, while OWL remains the formal semantic model rather than a classification API.
- Consolidated the public semantic API around `SemanticProfile`, semantic dimensions, and semantic classification; removed the former ontology-classification terminology from workflow, CLI, and application services.
- Versioned **Semantic Profiles independently from classification tasks**. Classification tasks now select dimensions from a referenced profile, while AtlasData and public semantic annotations refer to the profile rather than to an inference task.
- Aligned production semantic classification with the same versioned task and prompt contracts used by qualification, while retaining a single-model production execution policy.
- Separated Applicability **presence** from optional downstream detail semantics so central qualification and selective enrichment can evolve independently.
- Reduced the current central Applicability cascade to a single **presence** decision, removed polarity and structural subtype projection from voting, confidence, escalation, diagnostics, and archived consensus reports, and activated the one-prompt task-2.5.0 cascade.
- Migrated the Applicability Golden Corpus to the strict Presence-only schema 3.0, added an explicit deterministic schema-2.1 migration with a separately versioned partial detail seed, and reduced Golden regression, hard-case selection, framing reports, review CSVs, and current prediction snapshots to Presence-only contracts.
- Added sparse Applicability detail enrichment for final Presence-positive clauses, with a dedicated multi-label task and prompt, exact source evidence, qualification-coverage validation, deterministic selection, per-clause failure isolation, resumable results, managed-runtime ownership, and separate provenance that never changes the central Presence consensus. Integrated it as a recoverable post-consensus workflow stage and require its current, complete, manifest-bound results before immutable archival; archives include the routing consensus, detail resources, clause evidence, and a validated summary.
- Hardened Applicability detail target verification so non-clause targets are accepted as `not_confirmed` even when providers emit surplus detail, clause/requirement applicability has existential priority in mixed clauses, and unsupported or ungrounded function evidence is pruned instead of turning otherwise usable target decisions into validation failures.
- Replaced the former responsibility dimension with **role semantics** and structured actor–relation-class–target tuples; separated role-presence qualification from relation-tuple consensus and added golden-corpus evaluation.
- Made multidimensional qualification cascade-aware per dimension, including majority-based knowledge escalation, dimension-specific model eligibility, challenger qualification, reproducible HITL evidence, and immutable run archives.
- Preserved structural evidence, exact task/prompt/ontology inputs, model identity, analysis provenance, and qualification artifacts so runs can be reproduced and audited.

### Formal semantics and GraphRAG foundation

- Introduced a provider-neutral **Formal Semantic & Context Model** with versioned Standards Atlas Core and Functional Safety OWL ontologies.
- Added deterministic **ABox/CBox projection** from canonical `EngineeringDocument` data, covering document structure, Knowledge Domains, semantic taxonomy context, applicability, normative context, lineage, resolved relations, and standard-defined primary-subject context.
- Added an open subject vocabulary from AtlasData terms and deterministic clause subject identification; `Enrich Document Context` now materializes the resulting subject context for every clause while retaining LLM routing only for scope/reference candidates.
- Added ontology-guided concept and relation extraction constrained to declared OWL classes and properties, with confidence and provenance kept in rebuildable semantic-extraction artifacts rather than canonical documents.
- Integrated semantic extraction into qualification, including ontology-conformance checks, per-clause failure isolation, bounded retries/timeouts, progress reporting, undeclared-term diagnostics, and archival of extraction evidence.
- Refined the Functional Safety ontology from qualification evidence with explicit part/whole relations and additional system, requirement, specification, quantity, fault, error, and failure concepts.

### Document, family, table, and publication model

- Separated canonical **physical documents** from rebuildable **family publication views**. Multipart standards are composed on demand into runtime-only publication projections; `.atlas/data/documents` contains only physical parts.
- Added manifest-driven family-aware Docling onboarding with per-part publication metadata and part-aware clause identity.
- Promoted tables to first-class document structure and implemented the table pipeline: structural capture → deterministic `NormalizedTable` → structured `KnowledgeTable` mapping → provider-neutral retrieval projection.
- Added table-aware semantic extraction and provenance handling for large standards tables such as IEC 61508 technique/measure matrices.
- Hardened hierarchical Doorstop/Markdown publication, identifier generation, cross-document references, structural scope relations, and distinction between headings and document titles.
- Kept generated publication views rebuildable and qualification focused on physical source documents rather than aggregate family documents.

### Workflow, storage, schemas, and architecture

- Established explicit generated-data lifecycle boundaries: persistent machine state in `.atlas/data`, disposable cache data in `.atlas/cache`, rebuildable/intermediate workflow state in `.atlas/work`, and human-facing review/output under `local/`.
- Unified workflow task selection and typed manifest handling; made structural/document stages deterministic and assigned LLM-backed semantic classification explicitly to qualification where appropriate.
- Hardened workflow recovery, overwrite/fresh semantics, model lifecycle management, qualification limits, and Doorstop workspace handling.
- Established bounded schema compatibility: current-only writers, explicitly versioned persistent contracts, visible deprecation for supported readers, and no compatibility promise for disposable cache/work formats.
- Consolidated the ports-and-adapters architecture, package boundaries, CLI modules, qualification/proposal/normalization/alignment/Docling components, shared serialization/reporting infrastructure, ADRs, and UML documentation.

## 0.8.2 — Architecture policy baseline (2026-08-20)

- Introduced dimension-specific model eligibility and challenger qualification for the semantic qualification cascade.
- Established the storage lifecycle, taxonomy/task separation, schema compatibility policy, explicit ontology application boundary, structural-context taxonomy stage, and deterministic taxonomy → semantic/ontology ownership model that the subsequent refactoring completed.
- Strengthened structural reference/scope capture and reproducible qualification evidence.

## 0.8.1 — Modular qualification baseline (2026-08-05)

- Completed the first broad modularization of CLI, qualification, proposal generation, normalization, alignment, Docling processing, and shared infrastructure.
- Evolved semantic evaluation from a single role classifier into a multidimensional profile covering statement function, knowledge, process, applicability, and role/responsibility semantics.
- Added dimension-aware consensus/cascade processing, intermediate escalation, HITL review, structural-evidence fusion, scope inheritance, and public semantic gold annotations.
- Added visual-formula preservation and MCP-assisted formula transcription with provenance.
- Introduced structured table semantics and semantic-evaluation eligibility as the precursor to the later first-class table pipeline.

## 0.7.x — Canonical document and qualification architecture (2026-07-23 to 2026-08-04)

- Established deterministic `NormalizedDocument` and canonical `EngineeringDocument` contracts, AtlasData governance, workspace/publication architecture, and structured Markdown/Doorstop export.
- Added provider-independent LLM infrastructure, managed RamaLama lifecycle/GPU coordination, semantic evaluation services, and a secure interoperable MCP adapter.
- Built the reproducible evaluation stack: representative corpora, annotation contracts, proposal diagnostics, clause-reference context, qualification metrics, Codex integration, multidimensional qualification matrices, adaptive execution, consensus, and HITL workflows.
- Enforced ports-and-adapters dependency direction, narrowed service APIs, removed legacy `Clause.text` compatibility, modularized workflow/CLI boundaries, and synchronized ADR/UML documentation.
- Added deterministic internal and cross-document clause-reference materialization and normative inference from document structure.

## 0.6.x — Pipeline and composition foundation (2026-07-13 to 2026-07-21)

- Introduced structured clause content, reproducible Docling PDF extraction, deterministic normalization, clause-reference candidate detection, deterministic AtlasData alignment, and HITL alignment review.
- Added multipart-document support, document composition, semantic-role onboarding, and structured Markdown export.
- Consolidated the Python 3.13 / 0.6 architecture around a canonical engineering-document pipeline and AtlasData compatibility.

## Initial architecture — Canonical domain model (2026-07-07 to 2026-07-11)

- Created the Python project and AtlasData adapter, then introduced the canonical engineering-document domain model and compiler-style architecture.
- Added importer/exporter ports, application services, transformation pipelines, file-backed repositories, round-trip workflows, and the first annotation model.
- Established the architectural direction that later evolved into the current ports-and-adapters, deterministic preprocessing, qualification, and formal-semantics pipeline.
