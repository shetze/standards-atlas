# Evaluation and qualification

Standards Atlas separates deterministic document context from qualified semantic inference.
The current production semantic scope is intentionally narrow after the semantic-core refactoring.

## Current qualified semantic tasks

The active qualification paths are:

- **Applicability presence**: determine whether a clause explicitly carries clause-or-requirement applicability semantics. The current golden corpus and qualification path do not qualify polarity.
- **Formal semantic knowledge extraction**: propose source-bound engineering entities and normative assertions for the assertion-centred knowledge model.

Structural taxonomy, clause type, normative status, references, context routing and subject context are separate inputs. They are not reconstructed as legacy semantic labels.

## Applicability

Applicability is persisted as `enrichments.applicability` and is independent from other semantic enrichment. Accepted applicability is visible to downstream CBox consumers but excluded from the input fingerprint of a new applicability qualification run so that an accepted result cannot trigger or bias its own re-qualification.

The active qualification manifest is:

```bash
uv run standards-atlas workflow run \
  --task qualification \
  --manifests manifests/standards.yaml,manifests/applicability-presence-qualification-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

Detailed applicability analysis and evaluation commands remain available under `standards-atlas evaluation`.

## Assertion extraction

The assertion-centred model uses `KnowledgeEntity`, `NormativeAssertion` and `EvidenceAnchor`. Model output is a proposal, not canonical knowledge. Assertions become canonical only through the qualification/adoption boundary and retain source and provenance bindings.

The former semantic-extraction qualification command was removed in Slice 5C together with its entity/relation artifact contract. Assertion proposals are not treated as qualified knowledge until the assertion-centred qualification workflow introduced in Slice 7.

## Assertion review pilot (Slice 7D)

Slice 7D provides a deliberately small file-based pilot before the generic HITL workbench is
converted to assertion review. The existing applicability golden corpus is used **only to select
difficult clauses**. Its `expected.present` value is retained as provenance and is never converted
into an assertion expectation. The builder verifies clause id, document key and reference against the current `EngineeringDocument`.
The applicability corpus text is historical selection provenance, not assertion gold, so a text difference
does not block the build. The review artifact always embeds the **current** clause text and records both
the selection-text digest and whether it still matches exactly. This makes normalization/source drift
visible without forcing reviewers to annotate a stale pre-refactoring text representation.

For stratified selection, Atlas applies the assertion-review structural scope filter **before** sampling.
TOC/table/empty clauses, front matter, reference sections, bibliography/back matter, and CENELEC Annex ZZ
(including descendants) are excluded. Normative and informative engineering annexes remain eligible.
Explicit `--clause-id` selection remains an expert override and bypasses the stratified scope filter.

Build a deterministic 20-clause pilot (or repeat `--clause-id` for an explicit selection):

```bash
uv run standards-atlas evaluation assertion-review-pilot-build \
  --source local/review/applicability/applicability-golden-corpus.yaml \
  --ontology-version standards-atlas-core@2.0.0 \
  --ontology-version functional-safety@2.1.0 \
  --limit 20 \
  --output local/review/assertions/pilot/assertion-review-pilot.yaml
```

Run the existing assertion cascade once per selected document. `--review-pilot` derives the exact
Clause IDs from the review artifact, so the later golden suite and proposal population stay aligned.
Assertion extraction, verification, escalation, and the review artifact use the same compact canonical
CBox projection. It includes parent/ancestor headings, sibling context, structural references, interpreted
reference routing (for example `provides_exception`), **governing scopes that reach the current clause**,
subject context, applicability and structural profile metadata. Scope declarations are stored on their source
clause, so the assertion CBox also projects the inverse view: accepted document/part/subtree/clause scope
declarations whose reach contains the reviewed clause. Conditions, exclusions and qualifications remain
source-bound context rather than being rediscovered by the assertion LLM.

The same projection derives a deterministic `normative_context`. Standards content defaults to `normative`
unless source-backed evidence identifies informative context. Whole-document/part governing scopes are accepted
only from the structural `Scope` region; ordinary requirements cannot become global context merely because routing
interpreted a phrase such as `this document`. Local `clause`/`subtree` reaches from ordinary clauses remain valid.
If a structural Scope clause has no generated scope routing, the CBox still gives it deterministic document reach
and extracts an explicit document-character statement such as "informative character only" directly from its
canonical source text. Stronger evidence otherwise comes from explicit clause/annex status and governing Scope
qualifications; ancestor and document/part headings beginning with `Guidelines`/`Guidance`/`Example`/`Description`,
term/terminology clauses and matching local headings provide further informative signals. Ancestor evidence is
resolved nearest-first from the current EngineeringDocument hierarchy and recorded explicitly in the CBox basis.
Labelled `NOTE`, `EXAMPLE`,
`DESCRIPTION`, `AIM`, `RATIONALE` and `REFERENCES` sections are represented as informative span overrides
inside an otherwise normative clause.
This context guides `normative_force`; it never creates an assertion without body evidence in the
selected source clause. Assertion CBox 1.3 also projects `associative_context` as a separate structural
framing channel. Text-bearing ancestors are carried directly. When the immediate structural parent has no
body, only that sibling group's first earlier substantive descendant is carried as a
`leading_substantive_descendant`; heading-only ancestors higher in the tree do not pull an introductory leaf
from another branch into the current clause. This lets an introductory leaf such as `12.3.1.1` provide the
engineering subject for later `12.3.1.x` siblings without pretending that unrelated `12.2.x` content belongs
to them or that the introductory leaf's normative statements govern its siblings. The synthetic document
root is not used as associative context, and duplicate source clauses are suppressed nearest-first.

Entity grounding is broader than assertion grounding: an entity may use an exact span from the local
clause body, the local heading, an ancestor heading, or a body/heading surface explicitly carried in
`associative_context`. `EvidenceAnchor.source_clause_id` identifies the clause that owns the evidence and
`EvidenceAnchor.source_kind` selects `body` or `heading`; offsets and hashes are validated against that
exact canonical surface. If an LLM declares the wrong entity evidence surface, deterministic recovery may
select another allowed surface only when the quote has exactly one exact occurrence across all allowed
entity-evidence surfaces. Ambiguous matches remain violations. Assertions do not use this recovery path and
remain grounded in the local `body` surface of their own source clause.
Associative context may therefore identify or frame engineering entities and improve retrieval/GraphRAG,
but it cannot manufacture or propagate a normative statement.

```bash
uv run standards-atlas evaluation assertion-cascade \
  --review-pilot local/review/assertions/pilot/assertion-review-pilot.yaml \
  --document-key EN50716 \
  --ontology-version standards-atlas-core@2.0.0 \
  --ontology-version functional-safety@2.1.0 \
  --efficient-model <model> \
  --verifier-model <model> \
  --escalation-model <model> \
  --cascade-run-id assertion-pilot-en50716 \
  --efficient-run-id assertion-pilot-en50716-efficient \
  --escalation-run-id assertion-pilot-en50716-escalation \
  --output local/evaluation/assertion-pilot-en50716-cascade.json
```

Attach the final cascade route and candidates for that document to the review artifact. Supply the
escalation proposal only when the cascade report contains an escalation source:

```bash
uv run standards-atlas evaluation assertion-review-pilot-attach \
  --review local/review/assertions/pilot/assertion-review-pilot.yaml \
  --cascade-report local/evaluation/assertion-pilot-en50716-cascade.json \
  --efficient-proposal .atlas/data/knowledge-proposals/assertion-pilot-en50716-efficient/EN50716.json \
  --escalation-proposal .atlas/data/knowledge-proposals/assertion-pilot-en50716-escalation/EN50716.json
```

Reviewers then set every case to `review_status: reviewed` and populate `expected.entities` and
`expected.assertions`. Entity IDs are case-local conveniences. Evidence is annotated with exact
`start_offset`/`end_offset` values in the embedded, verified clause text; publication computes the
content hash automatically. A reviewed case with empty `entities` and `assertions` is an explicit
negative assertion case.

Publish only after all selected cases have been reviewed:

```bash
uv run standards-atlas evaluation assertion-review-pilot-publish \
  --review local/review/assertions/pilot/assertion-review-pilot.yaml \
  --output local/review/assertions/pilot/assertion-golden-suite.yaml
```

Publication deterministically merges semantically identical case-local entities within each document
and emits the existing `AssertionGoldenSuite` schema. The applicability corpus itself is not migrated
or modified.

## HITL

The review-package infrastructure is retained as the generic human-review substrate. Legacy taxonomy, role, statement-function, knowledge-kind and process-function review campaigns have been removed. Future review packages should operate on assertion/evidence proposals rather than resurrecting clause-level classification labels.

## Removed legacy dimensions

The following are no longer production semantic dimensions:

- statement functions / primary function;
- knowledge kinds / primary knowledge kind;
- process functions / primary process function;
- role-semantics presence and role relations.

Old manifests, prompts, qualification campaigns, CLI commands and tests for these dimensions are intentionally not supported or migrated.

## Assertion auto-adoption eligibility

Slice 7C evaluates whether assertion candidates are eligible for later automatic adoption without
writing canonical knowledge. The command requires a versioned policy, Development and Holdout
golden suites plus their Slice-7A reports, the exact Slice-7B cascade report, and the exact efficient
proposal artifact. Supply the escalation proposal as well when the cascade contains escalated
clauses.

```bash
uv run standards-atlas evaluation assertion-auto-adoption \
  --policy cfg/evaluation/assertion-auto-adoption-policy.yaml \
  --development-golden local/review/assertions/development/assertion-golden-suite.yaml \
  --development-report local/evaluation/assertion-development.json \
  --holdout-golden local/review/assertions/holdout/assertion-golden-suite.yaml \
  --holdout-report local/evaluation/assertion-holdout.json \
  --cascade-report local/evaluation/assertion-cascade.json \
  --efficient-proposal .atlas/data/knowledge-proposals/efficient-run/DOC.json \
  --escalation-proposal .atlas/data/knowledge-proposals/escalation-run/DOC.json \
  --output local/evaluation/assertion-auto-adoption.json
```

The report distinguishes `auto_adoption_eligible` from `review_required`. A passing global gate still requires exact production assertion/entity evidence anchors and never
makes escalated assertions automatically eligible: escalation output has not been independently
re-verified in Slice 7B. Applying eligible decisions to `EngineeringDocument.knowledge` is a Slice-8
operation.

