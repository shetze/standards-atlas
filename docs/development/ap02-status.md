# AP02 status — Series C / S05-S06

Date: 2026-10-01.

## Scope and basis

Series C implements only AP02-S05 and AP02-S06 on top of the locally verified Series-B snapshot
`standards-atlas-current-202610011842.zip` (SHA-256
`06b1edce6389200b606357681d933986c2c07eef8948c5b219f1eb7ccdfdb609`). AP01 remains a frozen
comparison/audit path. No real LLM, verifier, cascade or embedding execution is part of this series,
and Series D has not been started.

The previously established contracts remain in force:

- `source-surface-resolution-v1`;
- `engineering-document-source-surfaces-v1`;
- `structured-context-candidates-v1`;
- `structured-context-selection-v1` with default profile `assertion-context-selection-v1`; and
- current assertion CBox contract `1.3`.

Series C adds the private source/input package contract `source-bound-context-input-v1`, its
text-free public binding `source-bound-context-binding-v1`, and a common multi-span evidence-use
contract for technically grounding entity and assertion evidence. The productive model-output and
verifier cut-over remains assigned to Series D.

## S05 — bound source package, fingerprints and stale checking

`application.context.input_binding` now binds the Series-B candidate inventory and selection to a
reconstructable private `ContextSourcePackage`. Four independent deterministic fingerprints are
kept instead of one circular catch-all hash:

1. **source state** — primary document binding plus resolved source-surface identity, origin,
   rendering/hash/offset and media status for the complete candidate inventory;
2. **candidate space** — hierarchy/sequence/reference-derived candidate paths, reasons and
   diagnostics, including candidates that were not selected;
3. **selection decision/policy** — versioned selection contract/profile, selected and omitted
   candidates, reach hints, gaps, budget and completeness; and
4. **actual input** — the exact ordered delivered excerpts with their private source text and
   canonical absolute offsets.

Accepted `DocumentKnowledge`, proposals, reports, runtime paths, timestamps and run ids are not
inputs to these source fingerprints. A newly introduced later exception therefore invalidates reuse
through source-state/candidate-space change even when the old selection did not contain it. Policy
or budget changes invalidate the selection binding separately.

The package stores the exact delivered text; hashes do not stand in for unavailable bytes. The new
filesystem repository persists packages immutably under a hash-addressed private area with `0700`
directory and `0600` file permissions. Public lineage can retain `ContextSourcePackageBinding`,
which contains hashes and identities but no protected text. Loading a binding whose package bytes
are absent returns no package rather than treating the hash as source availability.

`context-source-package` is registered as a current-only schema family at schema version 1. Package
validation recomputes all four fingerprints from the persisted content, so a payload cannot silently
carry stale fingerprint values.

## S06 — common multi-span grounding

`application.knowledge_proposal_extraction.grounding` now provides one evidence-use/selector core
for both entity and assertion candidates. `EvidenceUse` declares the exact package source ref,
verbatim quote, checked selector and proposed contribution. Supported selectors are:

- a unique exact occurrence in the declared delivered excerpt;
- a zero-based occurrence index validated against all exact matches in that excerpt; or
- explicit null-based, half-open canonical character offsets `[start, end)`.

Excerpt-relative matches are projected back to the canonical source surface through the bound
absolute excerpt start. Python decoded-character positions are used consistently, including Unicode,
emoji and CRLF. When offsets and a quote are supplied they must address the same text.

The resolver searches only the declared source ref in `ContextSourcePackage.input_surfaces`. It does
not search other package surfaces or the wider document to repair a declaration. A quote that exists
elsewhere, including an identical quote in another clause or source kind, does not ground. Multiple
evidence uses remain separate; they are never joined by filling gaps or by inserting ellipses.

If any declared span fails, the result is `complete: false`. Successfully checked sibling spans may
remain in the diagnostic result, but callers cannot treat that subset as completely grounded.
Grounding records technical binding only (`semantic_status: unassessed`) and does not confirm
semantic reach.

Body and heading inputs map to the existing `EvidenceAnchor` model. Existing table/formula source
handles and transcription/media status remain in the source package. The extractor's
`[Table omitted: ...]` display marker is explicitly non-citable. Series C does not invent a new media
`EvidenceAnchor`; text/visual media integration beyond the current anchor contract remains for the
already assigned later consumers.

## Compatibility and consumer boundary

The existing single-quote/local-CBox grounding functions remain unchanged for the current
pre-Series-D production path and historical AP01 consumers. Series C adds the new closed contract
beside them so S07 can perform the atomic productive cut-over. It does not alter the extractor
schema, verifier payload, cascade, adoption policy, Golden expectations, frozen AP01 resolver or
historical AP01 fingerprints.

## Tests actually executed in the implementation environment

Focused S05/S06 contract and schema gate after implementation:

```text
python -m pytest -q \
  tests/unit/application/context/test_input_binding.py \
  tests/unit/adapters/filesystem/test_context_source_package_repository.py \
  tests/unit/application/knowledge_proposal_extraction/test_multi_span_grounding.py \
  tests/unit/application/schema \
  tests/architecture/test_schema_contracts.py
462 passed
```

Broader Series-C regression, including the existing source/context and grounding/table tests plus
the historical AP01 offline regression boundary:

```text
python -m pytest -q \
  tests/unit/application/context \
  tests/unit/application/knowledge_proposal_extraction \
  tests/unit/adapters/filesystem/test_context_source_package_repository.py \
  tests/unit/application/schema \
  tests/architecture/test_schema_contracts.py \
  tests/integration/assertion_qualification/test_offline_regression_pipeline.py \
  tests/architecture/test_assertion_qualification_boundary.py
672 passed
```

Architecture suite:

```text
python -m pytest -q tests/architecture
125 passed
```

`python -m compileall` succeeded for the new/changed application and test modules. A direct
`python -m ruff check .` could not run because Ruff is not installed in the execution environment.
`uv run --offline ruff check .` was attempted but dependency resolution stopped because `jsonschema`
is absent from the offline uv cache. The transient `.venv` created by that attempt was removed.

A full `python -m pytest -q` run was also attempted with a five-minute execution limit. The environment
terminated the run while it was still progressing (about 6%); it is therefore explicitly **not**
reported as passed. The user's local `ruff` and complete `pytest` runs remain the authoritative
Series-C acceptance checks.

No test or implementation step called a real model, verifier service, cascade service or embedding
service.

## Next work

The next planned work is Series D / AP02-S07-S08 only after the user applies this delta and locally
checks `ruff` plus the full test suite. S07 performs the atomic productive output/parser/consumer
cut-over to the source-bound evidence-list contract; S08 binds extractor/verifier/cascade reuse and
release gates to the new input package. Series C intentionally does not begin either task.
