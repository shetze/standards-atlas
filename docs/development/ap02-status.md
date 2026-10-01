# AP02 status — Series D / S07-S08

Date: 2026-10-01.

## Scope and basis

Series D implements only AP02-S07 and AP02-S08 on top of the user-provided, locally verified
Series-C snapshot `standards-atlas-current-202610012034.zip` (SHA-256
`50ecf7812266e427601a7359b0fcb9f219690139a352491f566150c97839b79b`). The historical AP01
audit/evaluation path remains a separate frozen input. Series E has not been started.

The source/context contracts established by Series A-C remain authoritative, including
`source-bound-context-input-v1`, `source-bound-context-binding-v1`,
`structured-context-selection-v1` and selection profile `assertion-context-selection-v1`.
Series D activates those bindings on the productive extraction/verification/cascade path.

No real LLM, verifier service, cascade service, embedding service or model-quality experiment was
executed. Adapter/cascade tests use controlled fake gateways only.

## S07 — productive source-bound evidence-list cut-over

The productive extractor now uses request contract
`source-bound-knowledge-proposal-request-v1` and output contract
`source-bound-knowledge-proposal-output-v1`. Its structured schema requires a non-empty `evidence`
list for every entity and assertion. Each evidence use contains a bound `source_ref`, exact quote,
checked selector and proposed contribution and is grounded through the common Series-C multi-span
core into the existing `EvidenceAnchor` lists.

The current parser is a clean break. Legacy `evidence_quote`, `evidence_source_kind` and
`evidence_source_clause_id` fields are rejected even when mixed into an otherwise current payload.
The old productive single-quote/local-body grounding helpers and their obsolete unit test are
removed. No source declaration is silently repaired by searching another surface or the wider
document.

Source text is rendered only from the exact `ContextSourcePackage.input_surfaces`. CBox-derived
interpretation metadata remains available without the source-bearing `heading`, `ancestor_headings`
and `associative_context` fields, so it cannot form an unbound second source basis. Result ownership
stays target-clause-local while anchors retain their actual source clause and body/heading kind.

The verifier uses request contract `source-bound-assertion-verifier-request-v1`. It resolves every
entity/assertion anchor only inside the exact bound package supplied for verification. Parent
headings and other delivered clause surfaces are valid technical evidence forms; there is no
local-body-only rejection. Its prompt explicitly separates technical binding from semantic reach,
conditions/exceptions, normative force and the project's non-mechanical granularity policy.

`DocumentKnowledgeProposal` now carries text-free `ContextSourcePackageBinding` values, clause
attempts carry the concrete package hash, and proposal/native qualification/cascade provenance
carries request/output/source-binding contract IDs. The proposal repository roundtrip preserves
these bindings. The existing schema registry remains version-1/current-only; its generic
`document-knowledge-proposal` model/writer bindings cover the clean-break model shape, while the
already registered `context-source-package` family remains the private source-package schema.

The current Golden validator no longer imposes the obsolete rule that an assertion's evidence span
must be owned by the result clause. Golden result ownership and IDs remain clause-local, and no
Golden expected content was changed. The historical AP01 `FrozenSourceResolver` and audit reader
were not converted into the current source resolver.

### S07 gate

A consistent S07 split point was reached before S08 work. The direct-consumer gate covered the
knowledge-proposal extraction package, both LLM adapters with fakes, assertion qualification,
formal semantics, proposal persistence, schema tests, assertion-qualification CLI tests,
integration tests and architecture tests:

```text
654 passed in 29.49s
```

This is the completed D1=S07 gate; the delivery is nevertheless cumulative through S08.

## S08 — shared cascade basis and conservative release boundaries

`AssertionQualificationCascadeService` pre-binds one package per processed target. The efficient
extractor and verifier receive that same immutable package instead of independently rebuilding a
current CBox. A supplied package whose bound document revision no longer matches the current
`EngineeringDocument` is rejected as stale before use.

Escalation reuses the efficient package by default. A caller may deliberately provide a different
bound escalation context; in that case the report stores both package hashes and sets
`source_basis_changed: true`. This makes a source-basis change explicit rather than presenting two
runs over different inputs as equivalent.

The cascade result exposes the packages actually used. The existing assertion-qualification CLI
persists those packages through the private, hash-addressed source-package repository before writing
the proposal/report artifacts and checks that the persisted package hashes exactly cover the public
proposal bindings. This is provenance/persistence for the current proposal path, not canonical
knowledge adoption.

Auto-adoption remains fail-closed. Current production identity now includes the extractor request,
output and source-binding contracts; an old qualification report without those IDs cannot qualify
the new pipeline. The verifier request/source-binding identity is checked separately as well.
Technically exact evidence remains review-required when the bound selection is incomplete, exposes
source gaps, or an assertion/required endpoint entity relies on a foreign-clause span whose semantic
reach has not been separately confirmed. These gates do not infer Applicability or normative force.

Missing/unauthorized source state enters the package selection as an explicit gap and therefore
cannot become auto-adoption-eligible. A stale source package is rejected, an unsupported/unknown
contract is review-required, and an intentionally different escalation basis is recorded. Ordinary
candidate-level grounding/verifier failures continue through the existing per-clause diagnostic or
escalation path rather than turning into a claimed complete result.

### S08 gate

After S08 and the final clean-break/policy tests, the direct-consumer suite was rerun:

```text
python -m pytest -q \
  tests/unit/application/knowledge_proposal_extraction \
  tests/unit/adapters/llm/test_knowledge_proposal_extractor.py \
  tests/unit/adapters/llm/test_assertion_proposal_verifier.py \
  tests/unit/application/assertion_qualification \
  tests/unit/application/formal_semantics \
  tests/unit/adapters/filesystem/test_knowledge_proposal_repository.py \
  tests/unit/adapters/filesystem/test_context_source_package_repository.py \
  tests/unit/application/schema \
  tests/unit/cli/test_assertion_qualification.py \
  tests/integration/assertion_qualification \
  tests/architecture

662 passed in 27.35s
```

The final additions include explicit tests that a mixed old/new single-quote payload is rejected and
that a verifier with an unsupported old source contract cannot authorize a current source-bound
assertion.

## Additional checks and environment limits

`python -m compileall` succeeded for all changed Python application/test areas. A deterministic
line-length check over changed Python files found no line longer than 100 characters.

`python -m ruff check .` cannot run in the implementation environment because Ruff is not installed:

```text
/opt/pyvenv/bin/python: No module named ruff
```

An earlier `uv run ruff check .` attempt tried to resolve missing project dependencies and could not
reach PyPI for `docling`; its transient `.venv` was removed. No Ruff success is claimed.

A full `python -m pytest -q` run was also attempted with a five-minute execution limit. It was still
running at roughly 6% when the environment terminated the command, so the full suite is explicitly
**not** reported as passed here. The user's local `ruff` and complete `pytest` runs remain the
acceptance checks requested for this series.

## Scope deliberately not implemented

Series D does not add canonical adoption, new Golden annotations, new ontology/Applicability
semantics, external-evidence adoption, native source-package Golden evaluation, full proposal/
knowledge/projection/provider source-resolution roundtrips, new MCP tools or any AP03 model-quality
work. Those wider evaluation/persistence/source-access tasks remain assigned to Series E after the
user's local Series-D verification.
