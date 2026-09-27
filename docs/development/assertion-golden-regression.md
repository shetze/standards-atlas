# Assertion Golden Adoption & Regression (AP01)

## Contract status

Series A (S01-S03) and Series B (S04-S06) are implemented. Current schema families
remain at version 1; this is a clean break, not a migration reader for document-wide
golden suites or interim Series-A reports. The completed review pilot remains a separate,
supported audit contract. Publication and evaluation perform no source selection,
extraction, verification, cascade, embeddings, unification or canonical adoption.

The current report contract is `assertion-clause-local-v1`. Series C still adds the four
ontology-based work-product metrics and qualified error diagnoses; Series D closes the
end-to-end/reproducibility checks and the final private v8 baseline.

## Audit and fingerprint contract

`load_assertion_review_audit` reads the original bytes, rejects duplicate mapping keys
(including YAML merge collisions and JSON keys), validates the current review contract
and requires every case to be reviewed with an expected block. Case ordering must match
the selection; local IDs and assertion endpoints, embedded body hashes, context identity
and expected span bounds are checked. The editable `load_assertion_review_pilot`
continues to support pending reviews.

The audit SHA-256 is over the original bytes, never a model dump. A copy uses
`copy_assertion_review_audit`: identical existing bytes are accepted, different existing
content is never overwritten. Parsing and publication do not repair hashes or alter
annotations. Parsed review objects cannot mutate the bound bytes.

Canonical hashes use UTF-8 JSON, sorted mapping keys, `ensure_ascii=False`, compact
separators, finite JSON values and unchanged list order. No text normalization is applied
to fingerprint inputs.

* **Source fingerprint (`assertion-review-source-v1`):** canonical hash of a mapping
  containing `contract`, `document_key`, `clause_id`, `reference`, `canonical_reference`,
  `text`, `text_sha256`, and the complete embedded `context`. This binds headings,
  ancestors and sequence order but excludes expected knowledge, proposal and review
  status.
* **Snapshot fingerprint (`assertion-review-snapshot-v1`):** canonical hash of the actual
  embedded proposal mapping, before adding parser defaults. An absent/null mapping has no
  fingerprint; an explicitly empty candidate set inside a valid snapshot does.
* **Declared proposal hash:** the original snapshot's `proposal_sha256` binds the
  historical full-document proposal. Without that artifact this is an unverified
  declaration, not a hash of the local snapshot.

The frozen review context is not proof of the fully rendered historical model input.
Missing model/prompt/input provenance stays unavailable. Context quotations are not
silently promoted to complete foreign clause bodies.

## Clause-local publication and candidate inputs

Entity and assertion identity is local to `(source_document_key, clause_id)`. Human
labels/IDs, objects, force and expected spans are never rewritten to improve a
measurement. Duplicate local IDs across different cases are allowed.

`AssertionGoldenSuite.audit` binds the review ID/version and original SHA-256. Each case
requires `source_document_key`, `clause_id`, review `reference` and `canonical_reference`,
`text_sha256`, `source_sha256`, `entities` and `assertions`. Case order is review selection
order. There is no document grouping, label trimming, global deduplication, ID rewriting
or legacy document-wide reader. Expected assertion evidence is enriched only with its
known source identity/kind and the SHA-256 of the unchanged review-text slice.

`project_native_proposal` is the single clause selection implementation used by pilot
attachment and native evaluation. A case receives assertions owned by that clause, their
endpoint entities, and entities explicitly assigned to that clause by
`proposal_clause_ids`. Diagnostics are filtered by their clause IDs. Unselected clauses
and clauses merely named in evidence do not create cases.

`assertion-evaluate` requires exactly one candidate option: repeatable `--proposal` or a
single `--review`. `--source-review` is optional and valid only alongside `--proposal`;
it verifies the frozen audit/source binding but does not change candidate mode. A review
input requires a snapshot for every golden case, including snapshots with empty results.
Both inputs project into `ClauseEvaluationCandidate` and use exactly the same matcher and
aggregator. Review reports remain Development regression material and are rejected by the
auto-adoption qualification boundary.

The report carries `candidate_mode`, `source_binding`, clause-local candidate fingerprints
and explicit provenance. Missing native document inputs stay `missing`, produce false
negatives and reduce `candidate_clauses`; they are not fabricated empty predictions.
Aggregate `clauses`, distinct `documents`, and `candidate_clauses` remain separate.

## Series B strict comparison contract

Strict label identity is Unicode NFKC normalization, casefolding and collapsed whitespace.
It is not paraphrase matching: negations, conditions, numbers, units and restrictions are
not removed. Runtime IDs and input ordering are not semantic match keys.

* `entities` is class-independent strict entity recognition by normalized label.
* `typed_entities` is the stricter label-plus-exact-`class_iri` recognition view retained
  for consumers that previously gated typed entity recognition.
* `entity_class_accuracy` compares exact classes only on unambiguous one-to-one label
  alignments. A wrong class therefore remains a recognized entity plus a class error.
* Assertion identity is the directed subject/object endpoint identity plus exact
  predicate. Entity endpoints use class-independent entity identity. Literal endpoints
  retain literal kind, Python value type/value, datatype and language.
* `predicate_accuracy` uses unambiguous endpoint alignments. `normative_force_accuracy`,
  expected-span equality and full-assertion exactness use unambiguous strict relation
  alignments.

Matching is multiset based. Duplicate predictions remain additional objects; no set
conversion can erase them. Attribute alignment pairs a bucket only when it contains
exactly one golden and one candidate object. Any other two-sided multiplicity is reported
as `ambiguous`; the matcher does not choose a best-fit pairing to improve class,
predicate, force or evidence metrics. The report retains immutable alignment records with
the case, comparison rule and actual golden/candidate IDs. Diagnostic alignments do not
change strict P/R/F1 counts.

## Metric, denominator and aggregation contract

Every ratio is represented by `RatioMetric` with numerator, denominator, value and status.
Precision is undefined when `predicted == 0`; recall is undefined when `expected == 0`.
When both sets are empty, P/R/F1 are all `null`/`not_applicable`, while set equality can
still be exact. F1 is `2*TP/(expected+predicted)` whenever that denominator is non-zero.
Over-extraction is `FP/predicted`; under-extraction is `FN/expected`.

Attribute accuracies expose expected/predicted support, evaluated/correct counts,
ambiguous and unmatched counts, plus alignment coverage. With zero aligned objects,
accuracy is `null`: `not_applicable` when neither side has support and `not_evaluable`
when objects exist but no unique alignment is available.

Aggregate P/R/F1 and over-/under-extraction are recomputed from aggregate counts.
Attribute accuracies are recomputed from aggregate correct/evaluated supports. The main
report never averages rounded per-case percentages. Validators enforce identities such as
`FP = predicted - TP`, `FN = expected - TP`, case uniqueness and aggregate support sums.
CLI output renders null metrics as `n/a` together with their status/support.

The auto-adoption policy continues to apply its existing entity thresholds to
`typed_entities`, not the newer class-independent entity recognition metric. Its former
single grounding threshold is a clean-break field named
`min_evidence_span_exact_match_accuracy`; unknown ratio values fail normal threshold
comparison rather than being interpreted as success. Review-snapshot reports remain
ineligible regardless of thresholds.

## Frozen-source evidence integrity

When the exact review audit is supplied, `FrozenSourceResolver` registers only complete,
identifiable source surfaces that are actually frozen in that audit: the selected clause
body, its own heading, identifiable ancestor headings, and complete body/heading surfaces
from `associative_context`. Arbitrary quotations are not promoted to foreign clause
bodies. Multiple different texts for the same `(document, clause, source_kind)` remain a
`conflicting` source; no version is selected silently.

Every candidate entity/assertion evidence use receives a technical integrity result:

* `valid`: source surface exists and exact offsets/hash match;
* `invalid`: the addressed frozen surface exists but bounds or hash are wrong;
* `unavailable`: the complete source surface, offsets or hash are unavailable;
* `conflicting`: the frozen audit contains incompatible texts for that source identity.

Body and heading are distinct source surfaces even with identical offsets. Evidence in an
identifiable frozen context clause can therefore be technically valid although it is
outside the local case body. Without a supplied audit, candidate evidence is explicitly
`unavailable`, not guessed from current project data.

`evidence_integrity` is separate from `evidence_span_exact_match`. The latter compares the
exact source identity/kind/offset/hash span multiset annotated in the golden assertion on
an unambiguous strict relation alignment. A longer but technically valid candidate span
can therefore have valid source integrity and still fail exact expected-span equality.
Entity evidence has no golden span annotations and receives technical integrity checks
only; it is not treated as automatically correct or incorrect against absent annotations.
`semantic_evidence` remains `not_evaluated` because AP01 Series B has no explicit human
semantic-evidence judgement from which to derive such a score.

## Clause-level exact match

`clause_exact_match` compares exactly the fields annotated by the golden case: the
multiset of entity label/class pairs and the multiset of assertions including directed
endpoints, predicate, normative force and expected evidence spans. Confidence, rationale,
proposal/runtime IDs and unannotated entity evidence are excluded. A present empty
candidate can exactly match an intentionally empty golden case. A missing candidate input
has status `missing_candidate` and never becomes an exact success. The aggregate exact
match denominator is all golden cases, so missing input remains visible as failed coverage.

## CLI examples and offline boundary

Example private pilot commands (from the repository root):

```bash
uv run standards-atlas evaluation assertion-review-pilot-publish \
  --review local/review/assertions/assertion-pilot/0.1.0/assertion-review-pilot-v8-reviewed-complete.yaml \
  --output local/review/assertions/assertion-pilot/0.1.0/assertion-golden-suite.yaml

uv run standards-atlas evaluation assertion-evaluate \
  --golden local/review/assertions/assertion-pilot/0.1.0/assertion-golden-suite.yaml \
  --review local/review/assertions/assertion-pilot/0.1.0/assertion-review-pilot-v8-reviewed-complete.yaml \
  --output local/evaluation/assertions/assertion-pilot/0.1.0/assertion-qualification-v8.json
```

For native proposals, replace `--review` with one or more `--proposal` paths. Add
`--source-review <original-audit.yaml>` to verify frozen sources. Publish/evaluate protect
all input files against output path collisions, including symlink and hardlink aliases.
Application code can preserve an audit using `copy_assertion_review_audit`; never use the
editable review writer as an audit-preservation step.

The synthetic tests exercise publish/evaluate with gateway, extractor, verifier and
cascade construction blocked and network connections prohibited. No private standards
text or external runtime is needed for these tests. Series B adds no model configuration,
prompt, source selection or canonical adoption behavior.

The 20/51/24 private v8 pilot inventory remains the Series-A adoption basis. Series B does
not rewrite or re-run that pilot as a final AP01 baseline; the final deterministic v8
report and result note remain Series D work after the work-product/diagnostic extensions
in Series C.
