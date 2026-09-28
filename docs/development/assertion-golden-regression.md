# Assertion Golden Adoption & Regression (AP01)

## Contract status

AP01 Series A through D (S01-S10) are implemented. Current schema families remain at
version 1; this is a clean break, not a migration reader for document-wide golden suites
or interim reports. The completed review pilot remains a separate, supported audit
contract. Publication and evaluation perform no source selection, extraction, verification,
cascade, embeddings, productive unification or canonical adoption.

The current report contract is `assertion-clause-local-v1`. It includes the four
ontology-based work-product metrics, conservative diagnostic findings, deterministic
ontology bindings and the reproducibility protections described below. The private v8
Development baseline has been materialized without changing either the golden review or
the stored candidates.

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

## Series C work-product metrics and diagnostics

Work-product membership is derived only from the explicitly bound formal ontology
resources. `WorkProduct` and its transitive `rdfs:subClassOf` descendants count; the
ancestor `EngineeringArtifact` does not. The evaluator and proposal unifier share the same
deterministic class-hierarchy query rather than maintaining separate class lists. Each
qualification report binds the ordered ontology references to the exact packaged resource
path, ontology/version IRIs and resource SHA-256. Failure to load the bound hierarchy is an
evaluation error, never an empty WorkProduct population. No predicate-domain/range or
keyword inference is used.

The four report dimensions are:

* `work_product_precision`: strictly identity-matched expected WorkProducts among candidate
  entities actually typed in the WorkProduct family / all such candidate entities;
* `work_product_recall`: strictly identity-matched candidate WorkProducts / all expected
  WorkProducts;
* `work_product_class_accuracy`: exact concrete class on unambiguous identity alignments
  for expected WorkProducts. A same-label candidate typed only as `EngineeringEntity` is
  still evaluated and counts as a class error;
* `required_work_product_relation_recall`: exact directed `Requirement`-family → `requires`
  → `WorkProduct`-family candidate relations / all such golden relations. Literal objects,
  wrong direction/predicate and non-WP candidate classes do not satisfy the numerator.

Diagnostics are a separate case-local view and never change strict counts. Findings carry
case identity, actual golden/candidate IDs or a retained violation reference, one or more
controlled codes, observed difference, rule, origin and status. Unique class, predicate
and force differences can be `rule_based`. Technical invalid evidence can be a rule-based
`grounding_failure`; conflicting sources remain reviewable. Missing, additional or
ambiguous strict identities remain `needs_review` when the comparison alone does not prove
the semantic cause. An additional assertion is therefore not automatically
`invented_assertion`, and a missing strict label is not automatically proof that a concept
is semantically absent.

Retained proposal violation text may produce conservative `needs_review` suggestions for
`over_extracted_detail`, `note_over_extraction`, `list_over_atomization`,
`missing_assertion`, `invented_assertion`, `wrong_predicate`, `wrong_normative_force`,
`wrong_context_use`, `grounding_failure`, `conditional_semantics_loss` and
`missing_work_product`. Multiple codes can describe one cause, so code counts are not
distinct-error counts. `human_confirmed` is reserved for a real human annotation with an
annotation ID; deterministic comparison and proposal diagnostics cannot claim it. Heading
evidence alone is not a context error, and list-shaped output alone is not
`list_over_atomization`.

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
  --output local/evaluation/assertions/assertion-pilot/0.1.0/assertion-qualification-v8.json \
  --summary-output local/evaluation/assertions/assertion-pilot/0.1.0/assertion-qualification-v8-summary.md
```

For native proposals, replace `--review` with one or more `--proposal` paths. Add
`--source-review <original-audit.yaml>` to verify frozen sources. Publish/evaluate protect
all input files against output path collisions, including symlink and hardlink aliases.
Application code can preserve an audit using `copy_assertion_review_audit`; never use the
editable review writer as an audit-preservation step.

The synthetic tests exercise publish/evaluate with gateway, extractor, verifier and
cascade construction blocked and network connections prohibited. No private standards
text or external runtime is needed for these tests. A fresh-process integration test runs
the offline publish/evaluate sequence twice and requires byte-identical golden, JSON report
and Markdown summary outputs. The persisted report is then replayed through the same
evaluator. A stale golden schema and a byte-different audit bound to an existing golden are
rejected.

`--summary-output` is optional. It renders only persisted report facts and deterministic
hashes; it contains no timestamp or local input/output paths. Strict measured differences,
retained proposal diagnostics, historical verifier dispositions and `needs_review`
diagnostic suggestions are shown separately. The summary is not an additional metric
contract and cannot change the JSON report.

## Final private v8 Development baseline

The completed audit SHA-256 is
`eab6d6dfa30e7f5af2bb477f7c5bce19764d7f3459c403e27652ce6ff15d6fa1`. Publication yields
20 cases across 9 documents with 51 expected entities and 24 expected assertions. The
deterministic golden model hash is
`80735a6045000b3749edda3fb67458607d36be54b243625348e821743a93ae74`; the deterministic
report model hash is
`4063bf29d640de7d9c06659e7eb95ce8b1080353e84e2e31e78b76bad4ab8063`. Two fresh CLI runs
produced byte-identical golden/report/summary artifacts, and report replay from the stored
golden plus original audit is equal to the persisted report.

The historical v8 output is a deliberately uncorrected baseline. Strict entity-label
P/R/F1 is 1/60, 1/51 and 2/111 (about 0.0167/0.0196/0.0180). Assertion TP is 0 with 15
predicted and 24 expected; clause exact match is 0/20. WP precision has denominator zero
and is therefore not applicable, WP recall is 0/7, WP class accuracy is not evaluable, and
required WP relation recall is 0/3. Technical evidence integrity is 75/75 valid; semantic
evidence remains `not_evaluated`. The report retains 61 proposal violations and 149
`needs_review` diagnostic findings without converting those observations into human
confirmation or a quality gate.

## AP02/AP03 handover

AP02 owns the productive gaps exposed by this frozen baseline: multi-source/multi-span
grounding, own and ancestor headings, sequential clause context, reach-aware context use,
missing-source semantics and explicit context-revision binding. Those future sources must
not be retrofitted into the historical v8 snapshots. AP03 receives the fixed Development
golden, evaluation contract, full v8 report and unresolved diagnostics for new model/prompt
experiments; the 20 known Development cases are not a holdout.
