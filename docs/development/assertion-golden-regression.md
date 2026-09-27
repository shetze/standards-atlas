# Assertion Golden Adoption & Regression (AP01)

## Contract status

Series A implements S01–S03 only. Current schema families remain at version 1;
this is a clean break, not a migration reader for document-wide golden suites.
The completed review pilot remains a separate, supported audit contract.
No source selection, extraction, verification, cascade, embeddings, unification
or canonical adoption is performed by publication/evaluation.

## Audit and fingerprint contract

`load_assertion_review_audit` reads the original bytes, rejects duplicate mapping
keys (including YAML merge collisions and JSON keys), validates the current
review contract and requires every case to be reviewed with an expected block.
Case ordering must match the selection; local IDs and assertion endpoints,
embedded body hashes, context identity and expected span bounds are checked.
The editable `load_assertion_review_pilot` continues to support pending reviews.

The audit SHA-256 is over the original bytes, never a model dump. A copy uses
`copy_assertion_review_audit`: identical existing bytes are accepted, different
existing content is never overwritten. Parsing and publication do not repair
hashes or alter annotations. Parsed review objects cannot mutate the bound bytes.

Canonical hashes use UTF-8 JSON, sorted mapping keys, `ensure_ascii=False`,
compact separators, finite JSON values and unchanged list order. No text
normalization is applied to fingerprint inputs.

* **Source fingerprint (`assertion-review-source-v1`):** canonical hash of a
  mapping containing `contract`, `document_key`, `clause_id`, `reference`,
  `canonical_reference`, `text`, `text_sha256`, and the complete embedded
  `context`. This binds headings, ancestors and sequence order but excludes
  expected knowledge, proposal and review status.
* **Snapshot fingerprint (`assertion-review-snapshot-v1`):** canonical hash of
  the actual embedded proposal mapping, before adding parser defaults. An
  absent/null mapping has no fingerprint; an explicitly empty candidate set
  inside a valid snapshot does. Missing defaults and explicit defaults can
  therefore have distinct snapshot fingerprints.
* **Declared proposal hash:** the original snapshot's `proposal_sha256` binds
  the historical full-document proposal. Without that artifact this is an
  unverified declaration, not a hash of the local snapshot.

The frozen review context is not proof of the fully rendered historical model
input. Missing model/prompt/input provenance must stay unavailable. Context
quotations are not silently promoted to complete foreign clause bodies.

## Comparison target and phased implementation

Entity and assertion identity is local to `(source_document_key, clause_id)`.
Human labels/IDs, objects, force and expected spans are never rewritten to
improve a measurement. Duplicate local IDs across different cases are allowed.

Series B will separate strict identity matching from diagnostic alignment,
attribute metrics, explicit null denominators and multi-source evidence checks.
The specified label comparison is NFKC + casefold + collapsed whitespace, not
paraphrase matching; negations, conditions, numbers and restrictions remain.
Diagnostic hints must never improve strict metrics. Series C adds ontology-based
work-product metrics and qualified error diagnoses. Series D closes end-to-end
reproducibility and the final private pilot baseline.

## Series A native publication/evaluation contract

`AssertionGoldenSuite.audit` binds the review ID/version and original SHA-256.
Each case requires `source_document_key`, `clause_id`, review `reference` and
`canonical_reference`, `text_sha256`, `source_sha256`, `entities` and `assertions`.
Case order is review selection order. There is no document grouping, label
trimming, global deduplication, ID rewriting or legacy document-wide reader.
Expected evidence is enriched only with document/clause identity, `body` source
kind and the SHA-256 of the exact existing slice of review text.

`project_native_proposal` is the single clause selection implementation used by
both pilot attachment and native evaluation. A case receives assertions owned by
that clause, their endpoint entities, and entities explicitly assigned to that
clause by `proposal_clause_ids`. Diagnostics are filtered by their clause IDs.
Unselected clauses and clauses merely named in evidence do not create cases.
Full-document proposal sources are listed once and may be referenced by multiple
case reports. Local candidate fingerprints exclude provenance and include the
actual projected candidate lists/evidence/diagnostics, preserving order.

The report requires `evaluation_contract: assertion-clause-local-interim-v1`,
`candidate_mode`, the audit binding and `source_binding`. Each case has its clause
identity, source fingerprint, candidate status, local candidate hash and explicit
provenance. Missing native document inputs remain visible as `missing`, with
false negatives and reduced `candidate_clauses`, rather than fabricated empty
proposals. Aggregate `clauses`, distinct `documents`, and `candidate_clauses` are
separate. Validators check identities, source references and aggregated counters.

**Interim metric semantics, not the final AP01 baseline:** `entities` still means
NFKC/casefold/whitespace-normalized label **plus exact class**, and assertion
endpoints use those typed signatures plus the predicate and owning clause.
Force/grounding/exact-assertion accuracy still use the existing multiset bucket
comparison, not the future ambiguity-aware attribute alignment. Grounding here
compares clause, source kind, offsets and declared span hash; it does **not**
resolve or validate actual candidate source text. P/R empty-denominator behavior
is deliberately unchanged until S05 (including 1.0 for two empty sets).
`candidate_status`/coverage must therefore be consulted; these values are not a
completed clause-exact-match metric. There is no class-independent entity metric,
WP metric, semantic evidence judgement or final error diagnosis in Series A.
The current policy retains its typed meaning and checks coverage; partition
separation now includes entity-only and deliberately empty cases.

For native input, `--source-review` optionally verifies the exact audit and all
published golden expectations. It is never a candidate selector. Without it the
report says `source_binding: golden_declared`; with it, `audit_verified` means
the review-to-golden binding was checked, not that historical model inputs or
candidate evidence have been proven. Publish/evaluate protect their input files
against output path collisions, including symlink and hardlink aliases.

## Series A review-snapshot input and CLI

`assertion-evaluate` requires exactly one candidate option: repeatable `--proposal`
or a single `--review`. `--source-review` is optional and valid only alongside
`--proposal`; it does not change the candidate mode. CLI misuse returns exit 2
without writing an output. All candidate inputs, the golden and the source review
are protected against output overwrites.

The review input first verifies the original audit byte hash and a newly derived
suite against the supplied golden, including selection order and every expected
field. Changing only candidate data still changes the audit binding and is not
accepted as the same historical baseline. A missing snapshot is rejected; a
present snapshot with empty result lists remains present. Every stored snapshot
is evaluated, including escalated routes, failures, violations and low-confidence
candidates. These diagnostics are retained, not used to filter candidates or
reconstruct objects that no longer exist.

Both inputs use `ClauseEvaluationCandidate` and the same `evaluate_case` and
aggregation functions. The native/review adapters do not construct a synthetic
`DocumentKnowledgeProposal`. Candidate content fingerprints exclude provenance;
therefore equivalent candidate contents can match while their origin remains
correctly different. A review report contains no native proposal-source records.
Its discriminated provenance binds the exact audit and raw snapshot fingerprint,
retains historical run/route declarations, and marks unavailable original-proposal,
model and rendered-input verification explicitly. The auto-adoption policy rejects
review-snapshot qualification reports even with permissive quality thresholds.

Example private pilot commands (from the repository root):

```bash
uv run standards-atlas evaluation assertion-review-pilot-publish \
  --review local/review/assertions/assertion-pilot/0.1.0/assertion-review-pilot-v8-reviewed-complete.yaml \
  --output local/review/assertions/assertion-pilot/0.1.0/assertion-golden-suite.yaml

uv run standards-atlas evaluation assertion-evaluate \
  --golden local/review/assertions/assertion-pilot/0.1.0/assertion-golden-suite.yaml \
  --review local/review/assertions/assertion-pilot/0.1.0/assertion-review-pilot-v8-reviewed-complete.yaml \
  --output local/evaluation/assertions/assertion-pilot/0.1.0/assertion-qualification-v8-interim.json
```

For native proposals, replace `--review` with one or more `--proposal` paths.
Add `--source-review <original-audit.yaml>` to verify the frozen source binding.
Do not pass both candidate options. Application code can copy the immutable
original bytes with `copy_assertion_review_audit`; never use the editable review
writer as an audit-preservation step.

The synthetic test suite exercises publish/evaluate with gateway, extractor,
verifier and cascade construction blocked and network connections prohibited.
No private standards text or external runtime is needed for these tests. Actual
cascade commands retain their functionality and import their model adapters only
inside the executing command. Series A does not add any new model configuration.

The delivered private pilot report is marked `interim` in its path and bound to
the interim evaluation contract. The 20 cases / 9 documents, 51 expected entities,
24 expected assertions and all 60 / 15 saved candidate objects have been checked.
Two fresh CLI processes reproduce identical golden/report bytes. This demonstrates
the Series A input path, not completion of S04–S10 or the final AP01 metric contract.
