# AP02 status — Series E / S09-S10

Date: 2026-10-01.

## Scope and basis

Series E implements only AP02-S09 and AP02-S10 on top of the user-provided, locally verified
Series-D snapshot `standards-atlas-current-202610012139.zip` (SHA-256
`12e59d6b4d36f53891173c259599e11310eedcb5703f2190f36d2defa8046568`). Series F has not been
started.

The Series-D productive source-bound request/output contract remains unchanged. The historical AP01
review/audit path remains a separate frozen input. Series E does not add model execution, a second
evaluator, canonical adoption, a graph store, a new MCP/Chat tool family, an ontology change or an
external-evidence adoption boundary.

No real LLM, verifier service, cascade service, embedding service or model-quality experiment was
executed.

## S09 — native source-package evaluation in the existing clause-local evaluator

`AssertionQualificationEvaluator` remains the single clause-local evaluator. Native proposals can
now be evaluated with their actual `ContextSourcePackage` inputs. Candidate evidence resolves only
inside the package named by the proposal's `ContextSourcePackageBinding`; it never falls back to the
historical review source when a native package evaluation was requested. The existing
`FrozenSourceResolver` remains the resolver for the historical audit/review entrance.

Historical expected-source material and current candidate-source material are therefore independent
inputs. When both an unchanged historical audit and a current native package are supplied, the audit
is used only for the existing Golden binding and a text-free source-comparability report. Candidate
grounding still uses only current package bytes. A changed current source surface is reported as
`changed`; additional current context absent from the historical audit is counted separately instead
of being declared invalid merely because the older prompt did not contain it.

Source comparability is explicitly non-semantic. It does not change entity alignment, assertion
alignment, evidence-span exact match, clause exact match or any AP01 metric. The strict matching
implementation was not relaxed. Missing private package bytes produce a visible partial native
source binding and unavailable evidence rather than a hash-based availability claim or frozen-source
fallback.

Current review annotations can now identify assertion-evidence spans by source clause and by
body/heading surface. Historical spans that omitted those fields retain their original meaning:
selected-clause body. Publishing a current review preserves the reviewed source identity and hashes
the exact referenced review surface. This does not add entity-evidence annotations, change Golden
IDs/classes/labels or rewrite the historical audit.

Proposal snapshots attached to a current review retain their text-free source-package binding. The
existing `assertion-evaluate` command adds `--source-package-workspace` for native proposal runs; it
loads only packages referenced by the supplied proposals from the existing private package
repository. `--review` is never redirected to that current source workspace.

### S09 gate

```text
PYTHONPATH=src python -m pytest -q \
  tests/unit/application/assertion_qualification/test_evaluation.py \
  tests/unit/application/assertion_qualification/test_assertion_review_audit.py \
  tests/unit/application/assertion_qualification/test_review_pilot.py \
  tests/unit/cli/test_assertion_qualification.py

104 passed in 4.53s
```

The tests include current parent-heading evidence, a native current source that differs from the
bound historical audit, missing private-package bytes, unchanged strict span matching, reviewed
foreign-source span publication and the CLI package-workspace entrance.

## S10 — persistence, formal projection and bounded source access

Proposal and source-package persistence remain separate: proposals retain only text-free package
bindings, while the existing hash-addressed private package repository retains protected source
bytes. A combined roundtrip test proves that a reloaded proposal still resolves its exact private
package and that protected package text does not appear in the persisted proposal artifact.

Synthetic accepted `DocumentKnowledge` is roundtripped through the existing
`EngineeringDocument` repository and the existing formal projection repository. The new small
application-level `FormalProjectionEvidenceResolver` follows evidence IDs already retained on
`FormalAssertion` objects back to either canonical `DocumentKnowledge.evidence_anchors` or existing
document artifact-lineage references. Knowledge anchors are then resolved through the existing
`SourceSurfaceResolver`; no GraphStore or new persisted graph model is introduced. Multi-ID
body/heading evidence and entity-only knowledge are covered. A projection or document with a
different document key is rejected at the resolver boundary.

The resolver accepts the existing `SourceAccessPolicy`. When source text is not authorized, an
evidence ID remains identifiable but its source text and textual hash metadata are not exposed. This
keeps evidence identity separate from disclosure permission.

Existing MCP tools/providers remain the external access surface; no tool names were added. Their
text boundary is tightened so `expose.clause_text: false` also redacts a clause heading, ancestor
headings and reference-mention source text, table titles/headers/cells and formula neighboring text.
The existing document allowlist is still enforced before access. Source path redaction remains
separate. Existing table/formula handles and their real availability/transcription states are not
converted into invented text evidence.

Canonical `EvidenceAnchor` remains same-document body/heading evidence. Series E does not widen that
model to unsupported external evidence; the existing EngineeringDocument validation and the new
resolver both stay inside the canonical document boundary.

### S10 / Series-E integration gate

```text
PYTHONPATH=src python -m pytest -q \
  tests/unit/application/assertion_qualification \
  tests/unit/application/formal_semantics \
  tests/unit/application/context/test_source_surfaces.py \
  tests/unit/adapters/filesystem/test_context_source_package_repository.py \
  tests/unit/adapters/filesystem/test_knowledge_proposal_repository.py \
  tests/unit/adapters/filesystem/test_formal_semantic_projection_repository.py \
  tests/unit/adapters/filesystem/test_document_repository.py \
  tests/unit/adapters/evaluation \
  tests/unit/adapters/mcp \
  tests/unit/application/schema \
  tests/unit/cli/test_assertion_qualification.py \
  tests/architecture

700 passed, 3 skipped in 10.96s
```

`python -m compileall` also succeeded for all changed application and test areas. A deterministic
line-length check over changed Python files found no line longer than the configured 100 characters.

## Environment limits

Ruff is not installed in the implementation Python environment. `python -m ruff check ...` reports
`No module named ruff`. An attempted `uv run ruff check ...` tried to resolve missing dependencies
from PyPI and failed because the environment has no network/DNS access; its transient `.venv` was
removed. No Ruff success is claimed.

A complete repository-wide `pytest` run was attempted with `PYTHONPATH=src python -m pytest -q`
but exceeded the 300-second execution limit before completion. No failure had been emitted before the
timeout, but the incomplete run is not reported as passed. The affected evaluation, persistence,
projection, provider/access, schema, CLI and architecture paths are covered by the 700-test
integration gate above. The user's requested local `ruff` and full `pytest` runs remain the acceptance
checks.

## Handover boundary

Series E is complete at the requested S09/S10 boundary. The native evaluator now has a real current
source-package entrance without changing historical expectations; proposal/package and synthetic
knowledge/projection roundtrips preserve evidence identity; existing access paths apply text release
to contextual source text. AP02 Series F (S11/S12 reference matrix and final inspection/handover)
remains unstarted.
