# AP02 status — Series B / S03-S04

Date: 2026-10-01.

## Scope and basis

Series B implements only AP02-S03 and AP02-S04 on top of the locally verified Series-A snapshot
`standards-atlas-current-202610011743.zip` (SHA-256
`386d72d70a83532a69c3b772a304f9d1e53213f0fb938d140a2eba97ae039386`). AP01 remains a frozen
comparison/audit path. No real LLM, verifier, cascade or embedding execution is part of this series,
and Series C has not been started.

The Series-A source contracts remain in force:

- `source-surface-resolution-v1`;
- `engineering-document-source-surfaces-v1`; and
- current assertion CBox contract `1.3`.

## S03 — hierarchical, sequential and reference candidates

Series B adds `structured-context-candidates-v1` in the application context layer. Candidate
construction uses the canonical EngineeringDocument order, real parent links and existing reference
metadata, resolving actual text surfaces through the Series-A `SourceSurfaceResolver`.

Implemented behavior:

- own body and heading are explicit source candidates;
- the complete resolvable ancestor path is retained, including textless/heading-only nodes;
- same-parent leaf sequences are considered in both directions using document order rather than
  lexical clause-number sorting;
- the first leaf is marked only as `first_leaf_candidate`, never as confirmed reach;
- direct internal reference targets and reverse references to the target or its same-parent sequence
  are candidates;
- another branch is not inherited merely through a more distant common ancestor;
- missing parents, cycles, order contradictions and unresolved/ambiguous references remain visible
  diagnostics; and
- external content is materialized only from an explicitly supplied, revision-bound source ref and
  remains subject to the source resolver's access policy. Resolver presence alone does not bind an
  external source and no network/edition lookup is performed.

All foreign candidates carry `reach_status: unconfirmed`. Candidate reasons and structural paths are
application metadata, not ABox predicates and not Applicability/normative-force inheritance.

## S04 — versioned selection, budget and gaps

Series B adds `structured-context-selection-v1` with default profile
`assertion-context-selection-v1`. The policy uses a deterministic character budget and separately
accounts for fixed and per-surface administrative/renderer overhead. Characters are not described as
tokens.

The selected/omitted manifest records source candidates, source paths, structural reach hints,
selection/omission reasons, known gaps and character costs. Foreign selected context always keeps
`semantic_reach_confirmed: false`.

Selection priorities are structural: target core first; reverse/direct references before unlinked
proximity; then ancestors; then same-parent sequence candidates by distance, considering forward
context before an equally distant backward candidate. First-leaf position and words such as
"except" do not create semantic reach. This prevents an explicitly later reverse reference from
being systematically displaced by an unlinked earlier introduction while still refusing to treat
ordinary later neighbors as confirmed restrictions.

Target content that exceeds the budget yields `input_budget_exceeded` and is not silently
truncated. Other complete surfaces that do not fit are explicitly omitted. Resolver-produced
addressed excerpts preserve their absolute offsets/hashes; Series B does not invent arbitrary
semantic excerpts to satisfy the budget. Unauthorized/conflicting/unloaded sources and unresolved
references remain visible gaps, so the resulting technical completeness state cannot be confused
with semantic approval or release readiness.

`assertion_context_selection(...)` exposes this path beside the existing
`assertion_cbox_context(...)`. The current CBox output remains unchanged (`1.3`) with its existing
Applicability, normative-context and attribute-provenance fields. The extraction service is not yet
wired to inject Series-B selection into a model request; source/input package binding remains S05 and
the productive output cut-over remains S07.

## Tests actually executed in the implementation environment

Before Series-B changes, the supplied snapshot passed this focused baseline:

```text
python -m pytest -q \
  tests/unit/application/context/test_source_surfaces.py \
  tests/unit/application/knowledge_proposal_extraction/test_assertion_context.py \
  tests/integration/assertion_qualification/test_offline_regression_pipeline.py \
  tests/architecture/test_assertion_qualification_boundary.py
21 passed
```

S03 gate:

```text
python -m pytest -q tests/unit/application/context/test_structured_candidates.py
5 passed

python -m pytest -q \
  tests/unit/application/context/test_source_surfaces.py \
  tests/unit/application/context/test_structured_candidates.py \
  tests/unit/application/knowledge_proposal_extraction/test_assertion_context.py
16 passed
```

S04/consumer gate and broader Series-B regression:

```text
python -m pytest -q \
  tests/unit/application/context/test_structured_candidates.py \
  tests/unit/application/context/test_context_selection.py \
  tests/unit/application/knowledge_proposal_extraction/test_assertion_context.py
15 passed

python -m pytest -q \
  tests/unit/application/context \
  tests/unit/application/knowledge_proposal_extraction \
  tests/unit/application/assertion_qualification \
  tests/architecture
446 passed

python -m pytest -q \
  tests/integration/assertion_qualification/test_offline_regression_pipeline.py \
  tests/architecture/test_assertion_qualification_boundary.py \
  tests/unit/application/assertion_qualification/test_assertion_review_audit.py
56 passed
```

`python -m compileall` succeeded for the changed application/test modules. A direct `ruff` binary is
not installed in the execution environment. `uv run --offline ruff check .` was attempted but did
not execute Ruff because the uv cache lacks the required `jsonschema` dependency. The attempt also
created a transient `.venv`, which was removed and is not part of the delta.

A full `python -m pytest -q` run was started, but the execution environment terminated it at its
runtime limit before completion. It is therefore **not** reported as passed. The user's local full
`pytest` and `ruff` runs remain the authoritative series acceptance checks.

## Next work

The next planned work is Series C / AP02-S05-S06 only after the user applies this delta and locally
checks `ruff` plus the full test suite. S05 should bind the already versioned candidate/selection
state into the source/input package and deterministic fingerprints; S06 should add the common
multi-span grounding contract. Series B intentionally does not start either task.
