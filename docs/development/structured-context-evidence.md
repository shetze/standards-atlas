# AP02 structured context and evidence contract

Status: Series D implemented baseline (AP02-S01-S08). This document describes the current
source-surface, structural-candidate, bounded-selection, source/input-binding and common multi-span
grounding contracts plus the productive source-bound extractor/verifier/cascade cut-over. Series E
remains responsible for the wider current-source evaluation, persistence/projection roundtrip and
provider/MCP source-resolution work.

## 1. Contract boundaries

AP02 keeps four identities separate:

1. the target clause that owns an interpretation result;
2. the clause and surface that own a piece of source material;
3. the structural reason why a source may later be selected as context; and
4. the reviewed semantic contribution of a source to an interpretation.

Series A implemented source identity and resolution. Series B added candidate discovery and
selection/reach policy. Series C binds the complete source/candidate/selection/input state and
provides the common technical multi-span grounding core. Series D now makes that source-bound
contract the only productive extractor/verifier/cascade path; the historical AP01 audit path remains
a separate frozen input.

The historical AP01 review/audit path remains byte-bound to its embedded source snapshots. Its
`FrozenSourceResolver` is not an adapter for current EngineeringDocuments and must never be
silently enriched from current project state.

## 2. Source identity and surfaces

The current source-surface contract is `source-surface-resolution-v1`. A source reference binds:

- `document_key` plus an optional expected source revision;
- the actual `clause_id` (the result-owner clause is not implied);
- for clause text, the existing `EvidenceSourceKind` (`body` or `heading`);
- for structured/visual media, `table` or `formula` plus the existing content-block id.

A successful resolution supplies the actual clause reference and a document binding containing:

- the known document year and version without guessing missing values;
- a deterministic source revision over source/structure-relevant EngineeringDocument state,
  excluding accepted knowledge and interpretation enrichments;
- the current EngineeringDocument artifact hash when lineage provides one.

A path or source locator alone is not treated as a revision. Body offsets address the exact
`Clause.plain_text` canonical projection; heading offsets address the exact stored heading. No
trimming, case folding or whitespace normalization is applied by the resolver before hashing or
slicing.

The current representation ids are intentionally narrow:

- `engineering-document-clause-body-v1`;
- `engineering-document-clause-heading-v1`;
- `engineering-document-table-handle-v1`;
- `engineering-document-formula-<representation>-v1`.

Body and heading deliberately reuse the existing Evidence source-kind vocabulary rather than a
parallel surface enum. Tables are exposed in Series A as structured source handles, not as a
newly invented flat text
surface. A visual-only formula is likewise a valid handle with `non_textual` availability. A
formula with a stored transcription/expression may expose that exact expression through its own
formula representation. Neither media surface is promoted to `EvidenceAnchor` in Series A.

## 3. Heading and content origin

Source availability is not evidence of source origin. Series A derives origin from existing
`KnowledgeStateProvenance` and, for content/media, existing `SourceEvidence`:

| Resolver origin | Meaning | Source-backed evidence status |
|---|---|---|
| `source_extraction` | Value is attributed to normalized/source extraction. | Source-backed canonical text. |
| `confirmed_source_assignment` | Attribute has explicit authority in clause provenance. | Source-backed canonical assignment; not a claim of byte-identical PDF text. |
| `deterministic_projection` | Value was deterministically created from other state. | Not automatically original source text. |
| `synthetic_display_label` | Value was created only as a display/selection label. | Display-only, never automatically original evidence. |
| `unresolved` | No sufficient origin is recorded, or origin is model/import-derived without explicit source authority. | Must not be promoted to original evidence merely because text exists. |

`ContentEnrichmentService` records `baseline.heading` as `source_extraction` whenever a detected
normalized heading is actually the basis of the canonical heading, including the case where the
same text had already been present as an AtlasData fallback. Part-selection fallback labels are
explicitly marked as synthetic display labels when they replace a missing part-root heading.

A confirmed editorial/canonical assignment remains distinguishable from a literal PDF claim.
Series A does not add a new verbatim-PDF contract.

## 4. Availability and access

Resolution uses the following technical states:

- `available`: the exact requested text surface/excerpt is bound and may be returned;
- `missing`: the requested clause/surface/block is absent;
- `not_loaded`: the requested document revision is not in the explicitly bound resolver set;
- `conflicting`: multiple loaded revisions match an unbound request, or an expected revision does
  not match the loaded source;
- `not_authorized`: the configured document/text access boundary denies the request;
- `non_textual`: a real media handle exists but Series A has no canonical textual surface for it.

Unauthorized responses contain no source text, text hash, excerpt offsets or source locator. The
resolver performs no network access and loads no implicit edition. Cross-document resolution is
possible only for documents explicitly passed into the resolver, and callers can require an exact
source revision.

## 5. Evidence use and multi-span grounding

Series C adds one technical evidence-use contract for entities and assertions. Each `EvidenceUse`
identifies one source ref from the exact bound input package, an unchanged quote, a checked selector
and a proposed contribution (`direct_statement`, `subject_frame` or `condition_or_exception`). The
contribution belongs to the *use*, not to the canonical anchor, and successful grounding keeps its
semantic status `unassessed`.

Selectors either require a unique exact quote, choose a validated zero-based occurrence inside the
declared delivered excerpt, or supply canonical half-open character offsets `[start, end)`. Exact
quotes and explicit offsets must agree. Repeated quotes without a disambiguating selector remain
ambiguous. Excerpt-local matches are projected to canonical source positions by the bound absolute
excerpt start; byte offsets or renderer-local character systems are not substituted silently.

Grounding is restricted to the declared surface/excerpt in `ContextSourcePackage.input_surfaces`.
No search of another heading/body or the complete document repairs a wrong source declaration. A
failed necessary span leaves the whole multi-span request incomplete; valid sibling spans are kept
only as diagnostics. Spans stay separate rather than being joined into a fabricated original quote.

Existing `EvidenceAnchor` lists remain the canonical destination for body/heading text. Existing
structured table/formula handles and transcription/media state remain preserved by the source
package. The extractor's table-omission marker is display metadata and is explicitly non-citable.
Series C does not invent new ABox predicates, Applicability logic, normative-force inheritance or
semantic reach confirmation.

## 6. Consumer matrix

| Consumer / boundary | Current restriction or capability | AP02 owner | Current AP02 action |
|---|---|---|---|
| `Clause` / `EngineeringDocument` | Canonical body/heading and attribute provenance already exist. | S01-S02 | Reuse unchanged persistence shape; fix heading writer provenance where source is known. |
| `DocumentKnowledge` / `EvidenceAnchor` | Entities/assertions already reference anchor lists; accepted anchors validate body/heading in the same document. | S06, S10 | S06 maps checked body/heading evidence uses to existing anchors; no parallel canonical anchor model or external adoption is introduced. |
| Canonical CBox / assertion CBox | Existing `1.3` data remains structural/interpretive metadata, while source-bearing text comes only from the bound source package. | S03-S07 | S03/S04 candidate/selection service feeds the S05 package; S07 removes source-bearing heading/body fields from the separate extractor interpretation context so CBox cannot become a second source truth. |
| Extraction renderer/schema/parser | Productive output is `source-bound-knowledge-proposal-output-v1`: entities and assertions both carry non-empty evidence-use lists over the bound package. | S07 | Cut over atomically. Legacy single-quote/source fields are not accepted by the current parser. |
| Grounding | The package-bound multi-span core is the productive entity/assertion grounding path. | S06-S07 | Old single-quote/local-body helpers are removed; no cross-surface repair or document-wide quote fallback remains. |
| Verifier | Verifier payloads resolve every entity/assertion anchor inside the same bound source package and may include body/heading spans from other supplied clauses. | S07-S08 | `source-bound-assertion-verifier-request-v1`; no local-body special case and no unbound document text. |
| Cascade / proposal lineage | Proposals bind one package per processed target; extractor and verifier share it, while an explicitly different escalation package is recorded separately. | S05, S08 | Stale document revisions are rejected; cascade reports retain extractor/verifier/escalation package hashes and `source_basis_changed`. |
| Auto-adoption policy | Runtime qualification identity includes request/output/source-binding contracts in addition to extractor/model/prompt identity. | S07-S08 | Old qualification identities cannot authorize the new contract; incomplete source context and unconfirmed cross-clause reach remain review-required. |
| AP01 Golden/review/evaluation | `FrozenSourceResolver` intentionally resolves only frozen audit surfaces. | S09 plus permanent AP01 guard | Keep unchanged; never enrich v8 snapshots with current sources. |
| Native evaluation | Clause-local projection preserves all anchor source-clause/source-kind identities and proposal reports carry the new runtime contract IDs. | S07, S09 | S07 removes the local-evidence validator restriction needed for current proposals; S09 still owns full native source-package evaluation/resolution. |
| Proposal persistence | `DocumentKnowledgeProposal` carries text-free package bindings and attempts carry the package hash used for that clause; private package bytes remain in the immutable repository. | S05, S07, S10 | Productive cascade CLI persists all bound source packages before proposal/report artifacts and verifies binding equality. S10 still owns the broader reload/projection proof. |
| Formal projection | Preserves evidence ids but later source-package reachability is not yet proven. | S10 | No graph/ontology change through Series D; S10 still owns the reload-to-source reachability proof. |
| Clause/evaluation provider | Exposes current EngineeringDocument clauses; not a general source resolver. | S02, S10 | Resolver remains application-layer and adapter-neutral. |
| MCP | Has document allowlist, clause-text exposure and source-path redaction. | S10 | Do not route MCP through the new resolver yet; carry equivalent access concepts without bypassing adapter policy. |
| Tables/formulas | First-class table ids and formula content blocks/source evidence already exist. | S02, S06, S10 | Preserve media handles/status; table display markers are non-citable and S06 does not invent a second extractor/transcription workflow. |
| Schema inventory | EngineeringDocument, proposal, context package and cascade/report contracts remain current-only clean-break schemas. | S05/S07 | New source-bound fields stay on schema-family version 1 as planned; strict models/tests distinguish the contract identity and no productive legacy output parser is added. |

Every current restriction above has an assigned AP02 slice. Series D closes the productive
output/parser/verifier/cascade and release-boundary cut-over. Series E/F still own the broader
evaluation/source-resolution roundtrip and end-to-end reference proof; those later capabilities are
not implied by the Series-D transport gates.

## 7. Structural reference cases established in Series A

These cases are technical contract examples, not new Golden semantic decisions:

- **T01 positive:** own source-extracted heading and body remain distinct resolvable surfaces.
- **T02 negative:** a synthetic/structural display label is not materialized as a heading source surface; an unresolved non-synthetic heading remains distinguishable from source extraction.
- **T03 negative:** an unattributed heading stays `unresolved` rather than being promoted by presence.
- **T17 negative:** identical text in heading/body or another clause remains bound to the declared
  source identity.
- **T24 media:** a visual-only formula remains a real handle with `non_textual` status; a textual
  formula retains its stored representation.
- **T32 access/edition:** a denied document returns no content, and a mismatched/ambiguous revision
  does not resolve to a convenient loaded edition.

Later slices add hierarchy, sequence, selection, budgets, bound packages and multi-span use without
changing these identity rules.

## 8. Series B structural candidate contract

The candidate inventory contract is `structured-context-candidates-v1`. It is built from the
canonical EngineeringDocument order, actual `parent_id` links, resolved reference metadata and the
Series-A source resolver. Candidate discovery is deliberately weaker than semantic reach.

For a target clause the inventory contains:

- own body and heading source surfaces;
- the complete resolvable ancestor chain, including heading-only or otherwise textless grouping
  nodes; ancestor body/heading surfaces remain separately addressable;
- the direct same-parent leaf sequence in canonical document order on both sides of the target;
- the first leaf as an explicit `first_leaf_candidate` reason only, never as a scope decision;
- direct internal reference targets; and
- clauses with reverse internal references to the target or to a same-parent sequence member that
  the target itself explicitly references. Reverse references to arbitrary other siblings do not
  become target context merely because all clauses share a large leaf group.

A sibling sequence never walks through a more distant common ancestor to borrow a descendant from
another branch. Missing parents, ancestor cycles, parent/order contradictions and unresolved or
ambiguous target references terminate deterministically and remain diagnostics. Reference paths
across section boundaries stay reference paths rather than synthetic sibling relations.

External references are identified, but resolver presence alone is not authorization. External
content becomes a candidate only when the caller supplies a concrete `SourceSurfaceRef` with an
exact `document_revision`; the normal Series-A source access policy is then applied. No document is
looked up from the network or by guessed edition.

Every foreign candidate has `reach_status: unconfirmed`. Candidate reasons and paths are
application-level structural metadata. They are not new ABox predicates, do not imply Applicability,
do not propagate normative force and do not say that a foreign assertion should be copied to the
target clause.

## 9. Series B selection and budget policy

The selection contract is `structured-context-selection-v1`; the default versioned profile is
`assertion-context-selection-v1`. The default policy uses a character budget with explicit fixed
and per-surface overhead reservations. It never reports characters as tokens. S05 now binds the
selected exact input surfaces and their deterministic input fingerprint; S07 remains responsible
for binding the complete rendered request.

Selection is deterministic and records selected and omitted candidates, structural reach hints,
selection reasons, known gaps, estimated character costs and a technical completeness state. The
state is not an adoption/release decision and all foreign selected entries keep
`semantic_reach_confirmed: false`.

Priority is deliberately structural rather than lexical:

1. target body and target heading are an all-or-nothing core for budget purposes when available;
2. direct references and target-linked reverse references are considered before unlinked proximity;
3. ancestor context follows; and
4. ordinary same-parent sequence candidates are ordered by distance, with forward context before
   equally distant backward context.

The first leaf receives no special selection priority merely because it is first. No word such as
`except` is used as a reach classifier. An explicitly later reverse reference therefore cannot be
systematically displaced by an unlinked earlier introduction, while an unlinked later neighbor is
still only an unconfirmed candidate. Existing CBox Applicability and normative-context projections
remain separate and unchanged; the selection policy neither copies nor inherits them into foreign
source entries.

If target content exceeds the configured budget, selection returns
`input_budget_exceeded` and does not truncate it. Other complete source surfaces that do not fit are
omitted with `budget_exceeded`. Pre-addressed resolver excerpts retain their absolute source offsets
and hashes; Series B itself does not invent a semantically arbitrary excerpt just to make text fit.
Unauthorized, conflicting, unloaded and unresolved sources remain explicit gaps rather than guessed
substitutes.

## 10. Consumer state after Series B

`application.knowledge_proposal_extraction.context.assertion_context_selection(...)` exposes the
new candidate/selection path beside `assertion_cbox_context(...)`. The current CBox remains contract
`1.3` and its existing `normative_context`, Applicability and provenance projections are unchanged.
The extraction service does not yet inject the new selection into a live model request. That
intentional boundary avoids an early S05/S07 cut-over while giving the next series one shared,
tested selection source instead of a second context truth.

The AP01 frozen audit resolver and historical Golden/evaluation contracts remain untouched. Series B
does not run or qualify a real extractor, verifier, cascade or embedding model.

## 11. Series C source/input binding and reuse contract

The private package contract is `source-bound-context-input-v1`; its public text-free reference is
`source-bound-context-binding-v1`. The persisted schema family is `context-source-package` version
1. Source bytes and hashes have different responsibilities: exact selected excerpts live in the
private package (or must otherwise be immutably resolvable), while public lineage may expose only
the package/content fingerprints. Possessing a hash never makes absent source bytes available.

Four fingerprint dimensions stay independent:

- **source state** includes the primary document binding and technical identity/origin/rendering/
  content/media status of every candidate source;
- **candidate space** includes hierarchy, order, reference paths, candidate reasons and diagnostics,
  including sources that selection omitted;
- **selection decision** includes the versioned profile/policy, selected and omitted entries, reach
  hints, gaps, completeness and budget accounting; and
- **actual input** binds the exact ordered delivered excerpts, their text and canonical offsets.

This means a newly inserted, previously unselected later exception changes source/candidate state and
invalidates reuse. A policy or budget change can invalidate the selection fingerprint without
pretending the underlying source revision changed. Accepted knowledge, proposals, reports, runtime
paths, timestamps and run ids do not participate in source fingerprints, preventing circular
knowledge/report provenance.

The filesystem repository stores canonical JSON under a content-derived path with private directory
and file permissions. On load it verifies the persisted byte hash, current schema and complete public
binding. Package model validation independently recomputes the four fingerprints from package
content.

## 12. Series C multi-span grounding contract

`EvidenceGroundingRequest` is common to entity and assertion candidates. Every declared evidence use
resolves only through its `source_ref` in the bound actual input. `UniqueQuoteSelector`,
`QuoteOccurrenceSelector` and `CanonicalOffsetSelector` make repeated text and explicit offsets
checkable without guessing. Overlapping occurrences are enumerated deterministically.

Offsets are null-based, half-open decoded Python-character offsets of the canonical source surface.
An excerpt retains its absolute source start, so Unicode, emoji, CRLF and leading whitespace do not
change the address system when a local match is projected back. An offset selector outside the
delivered excerpt or one that disagrees with the exact quote is rejected rather than repaired.

The common core never redirects a failed declaration to another source surface and never searches
text that was not supplied in the package. Identical quotes in different clauses or heading/body
surfaces therefore stay distinct. Multiple spans stay multiple anchors/uses; no filler text or
ellipses create a synthetic quote. If any required use fails, `complete` is false.

`[Table omitted: ...]` is an extractor display marker, not evidence. Real structured table/formula
handles remain represented in source resolution and the bound package together with their existing
media/transcription status. The current canonical `EvidenceAnchor` still addresses body/heading
text only; Series C preserves this limit rather than fabricating textual media evidence.

## 13. Consumer state after Series C

The new package and grounding contracts are closed and independently testable but are intentionally
not yet the productive LLM output contract. Current extractor schema/parser, verifier payload,
cascade/reuse gates and adoption policy remain on their pre-cut-over path until S07/S08 can migrate
the direct consumers atomically. The legacy helper path is therefore not advertised as a second new
format; it is retained only so Series C does not begin the Series-D cut-over.

The AP01 frozen resolver, Golden expectations and historical offline evaluation/fingerprints remain
unchanged. Series C performs no model execution and no semantic qualification; successful grounding
means only that declared evidence is technically bound to the delivered source text.



## 14. Series D productive evidence-list cut-over

The productive extractor request contract is `source-bound-knowledge-proposal-request-v1` and its
model output contract is `source-bound-knowledge-proposal-output-v1`. The renderer supplies source
text only through the exact `ContextSourcePackage.input_surfaces` represented in the request. The
separate interpretation context deliberately removes source-bearing `heading`, `ancestor_headings`
and `associative_context` fields; remaining CBox metadata may guide interpretation but is not an
independent evidence surface.

Both entities and assertions must return a non-empty list of evidence uses. Every declared use is
parsed through the common Series-C grounding core and maps to the existing `EvidenceAnchor` lists.
The target clause continues to own the proposal/assertion, while each anchor retains the actual
source clause and body/heading kind. One failed declared span rejects that candidate rather than
silently publishing its surviving subset. Legacy single-quote/source fields are not a second input
format and are rejected by the current parser. The old productive single-quote grounding helpers
are removed.

The verifier request contract is `source-bound-assertion-verifier-request-v1`. Candidate evidence is
re-rendered only by resolving its existing anchors inside the exact package used for verification.
Heading and foreign-clause evidence are valid technical forms when those surfaces were delivered;
there is no local-body test and no search elsewhere in the document. The verifier is instructed to
judge source ownership, combined meaning, conditions/exceptions, normative force and semantic reach
without demanding mechanical extraction of every context passage.

`DocumentKnowledgeProposal` now records text-free `ContextSourcePackageBinding` values and each
clause attempt records the concrete package hash. Request/output/source-binding contract IDs are
part of proposal provenance and are propagated into native qualification and cascade source
identity. Golden owner clauses remain clause-local, but Golden assertion evidence is no longer
artificially required to be owned by the same clause; no expected Golden content is changed.

## 15. Series D shared cascade basis and conservative release boundary

`AssertionQualificationCascadeService` binds the selected source packages before extraction. The
efficient extractor and verifier receive the same immutable package per clause. A supplied package
whose document revision no longer matches the current `EngineeringDocument` is rejected before use.
Escalation reuses the efficient package by default. If a caller deliberately supplies a different
bound escalation context, the cascade report records both package hashes and
`source_basis_changed: true` rather than presenting the runs as one source basis.

The cascade result exposes the private packages needed for persistence. The existing CLI saves those
packages through the private hash-addressed repository before writing the corresponding proposals
and report, and checks that the persisted package hashes equal all public proposal bindings. This is
source/proposal lineage only; it is not canonical knowledge adoption.

The auto-adoption boundary remains fail-closed. Development, Holdout and production must share the
full current runtime identity, including request/output/source-binding contract IDs. A qualification
artifact without those new IDs therefore cannot release a Series-D proposal. Even with exact
offsets/hashes, a candidate remains review-required when its bound selection is not `complete`,
reports source gaps, or relies on foreign-clause evidence whose semantic reach has not been
separately confirmed. Technically valid heading/context evidence is no longer misclassified as
non-exact merely because it is not local body text.

Series D does not add canonical adoption, new Golden decisions, external-evidence adoption, a new
ontology, Applicability logic or model-quality claims. The AP01 `FrozenSourceResolver` and historical
audit reader remain separate and unchanged. Full native source-package evaluation and persistence/
projection/provider roundtrip remain assigned to Series E.

## 16. Series E evaluator source separation

The clause-local evaluator now has two deliberately distinct source bases. Historical review
snapshots continue to resolve evidence through the byte-bound AP01 audit. Native proposals may
instead carry their current text-free `ContextSourcePackageBinding` values and be evaluated with the
matching private packages. When that native package entrance is selected, candidate evidence is
resolved only against the exact delivered package; historical source bytes are not a fallback.

A text-free per-case source comparison reports whether overlapping current source surfaces match the
historical audit (when supplied) or the Golden target-body hash. Additional current context is
reported separately. This comparison does not participate in semantic or span matching and cannot
improve AP01 metrics. Missing package bytes remain missing even when their public hash is known.

Current review assertion-evidence annotations can identify source clause plus body/heading kind.
Historical annotations that omit those fields remain selected-clause-body spans. Publication keeps
assertion ownership clause-local while preserving the reviewed evidence owner. No entity-evidence
annotation is synthesized.

## 17. Series E persistence, projection and source access

`DocumentKnowledgeProposal` and `ContextSourcePackage` retain their existing split persistence:
proposal artifacts expose only package bindings, while source text stays in the private
hash-addressed package repository. Reloading either artifact does not create a new source revision or
copy protected text into the proposal.

Formal projections already carry `evidence_ids`. `FormalProjectionEvidenceResolver` is a small
application resolver that maps those IDs back to canonical `DocumentKnowledge` anchors or existing
artifact lineage and then uses `SourceSurfaceResolver` for the real body/heading surface. It adds no
GraphStore and no new adoption state. The existing `SourceAccessPolicy` controls whether the
resolved source may expose text.

The existing MCP access surface remains unchanged in tool count. Text denial now covers clause body,
headings and ancestor context, source-text reference mentions, table textual content and neighboring
formula context. Document allowlists continue to gate clause/table/formula access. Structured table
and formula handles retain their actual status; Series E does not fabricate textual evidence from
markers, images or unavailable transcriptions.

## 18. Series F deterministic reference and inspection boundary

The completed structural reference contract is enumerated as `ap02-structural-reference-matrix-v1`
in `tests/fixtures/ap02/reference-test-matrix.json`. It binds AP02 reference intentions T01-T34 to
concrete public/offline pytest functions. The matrix is a test traceability artifact, not a Golden
suite and not a semantic scorecard. Architecture tests require the full T01-T34 set and verify that
all referenced pytest nodes continue to exist.

The model-free inspection application is `context-evidence-inspection-v1`. It composes the existing
candidate discovery, `structured-context-selection-v1`, `ContextSourcePackage` input binding and the
shared multi-span grounding service. The report is intentionally text-free and deterministic: it
shows target identity, source identities/origins, structural paths, selection and omission reasons,
gaps, configured/used budget, the four source/input fingerprints, package hash and one result per
explicit grounding request. It carries `model_execution: false` and
`semantic_quality_assessed: false` as contract invariants.

The CLI exposes this service as `standards-atlas context evidence-inspect`; it is a thin read-only
wrapper over persisted `EngineeringDocument` data. Optional grounding requests must use the current
`EvidenceGroundingRequest` contract and may address only surfaces actually delivered in the selected
package. The command writes no accepted `DocumentKnowledge`, performs no adoption and has no LLM,
verifier, cascade or embedding dependency.

The public Series-F integration fixture closes the deterministic path from source-surface resolution
through candidates, selection, bound package, fake structured extractor response, common grounding,
fake verifier/cascade, proposal/package persistence, the existing clause-local evaluator and formal
projection back to resolvable source surfaces. Synthetic accepted knowledge exists only inside the
test to exercise the already-existing projection boundary; it is not an adoption workflow.

AP03 receives the request/output/verifier contract IDs, source-package bindings, reference cases and
the explicit statement that model quality has not been assessed. AP05 receives source identities,
structural paths, addressable excerpts, budgets, gaps and the four fingerprint classes as retrieval
inputs; it is not required to copy the extractor prompt or its complete selected context into a
retrieval representation.


### Post-Series-F correction from real document inspection

Model-free inspections of IEC 61508-2/3, ISO 26262-2 and EN 50126-1 exposed two contract bugs that
were not visible in the original synthetic matrix. They are corrected without introducing AP03
model work:

- AtlasData structural display values such as `REQUIREMENT` and `OBJECTIVE` remain usable display
  metadata but no longer create body-independent `heading` source surfaces. A non-placeholder
  AtlasData title (for example a term title such as `hazard log`) is resolved as an
  `atlasdata-structure-title` confirmed source assignment when older documents have no more specific
  heading provenance. Explicit source-extraction/confirmation provenance still takes precedence.
- Reverse-reference discovery no longer treats every sibling in a potentially very large leaf group
  as an implicit target. Reverse edges are retained when they point directly to the target or to a
  local sequence member that the target explicitly references. This preserves HFT-style reciprocal
  references while preventing unrelated term/annex references from consuming target context budget.

The correction does not infer semantic reach. Selected foreign sources continue to carry
`semantic_reach_confirmed: false`, and unresolved natural-language range references remain visible
as gaps rather than being guessed.
