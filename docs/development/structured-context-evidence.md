# AP02 structured context and evidence contract

Status: Series A contract baseline (AP02-S01/S02). This document describes the current
source-surface contract and the consumer migration map. It does not activate the productive
multi-source extractor output contract.

## 1. Contract boundaries

AP02 keeps four identities separate:

1. the target clause that owns an interpretation result;
2. the clause and surface that own a piece of source material;
3. the structural reason why a source may later be selected as context; and
4. the reviewed semantic contribution of a source to an interpretation.

Series A implements only the first two as source-resolution prerequisites. Candidate discovery,
selection/reach policy, input packages and productive multi-span output remain assigned to later
AP02 slices.

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

## 5. Evidence-use and later contracts

The eventual productive contract will attach multiple evidence *uses* to entities and assertions,
with source reference, exact quote, selector and contribution semantics. Series A deliberately does
not change the current extractor schema or current proposal payload. Existing `EvidenceAnchor`
lists remain the canonical text-safe destination once S06/S07 introduce the new use/selector
contract.

Series A also does not define context selection, scope inheritance, normative-force inheritance or
new Applicability semantics. Source resolution answers only whether a requested source exists,
what it is, where it came from technically, and whether the caller may access it.

## 6. Consumer matrix

| Consumer / boundary | Current restriction or capability | AP02 owner | Series A action |
|---|---|---|---|
| `Clause` / `EngineeringDocument` | Canonical body/heading and attribute provenance already exist. | S01-S02 | Reuse unchanged persistence shape; fix heading writer provenance where source is known. |
| `DocumentKnowledge` / `EvidenceAnchor` | Entities/assertions already reference anchor lists; accepted anchors validate only against body/heading in the same document. | S06, S10 | No parallel anchor model and no external canonical adoption in Series A. |
| Canonical CBox / assertion CBox | Carries own heading, ancestor headings and bounded associative context, but source text and display context are not a common resolver contract. | S03-S05 | Keep current CBox contract unchanged in Series A; establish resolver underneath future selection. |
| Extraction renderer/schema/parser | Current model payload uses single quote declarations and legacy source fields. | S07 | No productive output cut-over in Series A. |
| Grounding | Exact matching exists; entity fallback may silently search other allowed CBox surfaces. | S06-S07 | Leave behavior untouched; S02 only provides reusable source resolution primitives. |
| Verifier | Payload/prompt still enforce local-body restrictions for assertions. | S07-S08 | No behavior change in Series A. |
| Cascade / proposal lineage | Does not bind a reusable source package shared with verifier. | S05, S08 | No behavior change in Series A. |
| Auto-adoption policy | Current grounding gates assume old contract identity. | S07-S08 | No gate relaxation in Series A. |
| AP01 Golden/review/evaluation | `FrozenSourceResolver` intentionally resolves only frozen audit surfaces. | S09 plus permanent AP01 guard | Keep unchanged; never enrich v8 snapshots with current sources. |
| Native evaluation | Clause-local proposal projection exists; current source package is not bound. | S09 | No evaluator change in Series A. |
| Proposal persistence | Repository persists current proposal schema; no bound context package yet. | S05, S07, S10 | No new alternative proposal format in Series A. |
| Formal projection | Preserves evidence ids but later source-package reachability is not yet proven. | S10 | No graph/ontology change in Series A. |
| Clause/evaluation provider | Exposes current EngineeringDocument clauses; not a general source resolver. | S02, S10 | Resolver remains application-layer and adapter-neutral. |
| MCP | Has document allowlist, clause-text exposure and source-path redaction. | S10 | Do not route MCP through the new resolver yet; carry equivalent access concepts without bypassing adapter policy. |
| Tables/formulas | First-class table ids and formula content blocks/source evidence already exist. | S02, S06, S10 | Reuse as media handles; no second extractor/transcription workflow. |
| Schema inventory | EngineeringDocument, proposal and AP01 contracts are current-only clean-break schemas. | S05/S07 when persistence changes | Series A adds no persisted schema family and no legacy reader. |

Every current restriction above has an assigned AP02 slice; Series A does not leave a known direct
consumer half-migrated because it does not activate the new productive payload.

## 7. Structural reference cases established in Series A

These cases are technical contract examples, not new Golden semantic decisions:

- **T01 positive:** own source-extracted heading and body remain distinct resolvable surfaces.
- **T02 negative:** a synthetic display heading is visible as display-only, not original evidence.
- **T03 negative:** an unattributed heading stays `unresolved` rather than being promoted by presence.
- **T17 negative:** identical text in heading/body or another clause remains bound to the declared
  source identity.
- **T24 media:** a visual-only formula remains a real handle with `non_textual` status; a textual
  formula retains its stored representation.
- **T32 access/edition:** a denied document returns no content, and a mismatched/ambiguous revision
  does not resolve to a convenient loaded edition.

Later slices add hierarchy, sequence, selection, budgets, bound packages and multi-span use without
changing these identity rules.
