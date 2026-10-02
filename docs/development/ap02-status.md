# AP02 status — Series F / S11-S12 complete

Date: 2026-10-02.

## Scope and basis

Series F implements only AP02-S11 and AP02-S12 on top of the user-provided, locally verified
Series-E snapshot `standards-atlas-current-202610020740.zip` (SHA-256
`c1eb23a08aac6a0b3363738cce24a7f06f0f77cdd54d0b225d9e62e655a8f24d`). It closes AP02; no AP03
or AP05 implementation is started.

The Series-E source-bound production/evaluation/persistence contracts remain the implementation
basis. Series F adds test traceability, one model-free inspection service/CLI and final handover
material. It does not add a new evaluator, adoption path, GraphStore, ontology, Applicability logic,
LLM strategy, verifier strategy or retrieval system.

No real LLM, verifier service, cascade service, embedding service or model-quality experiment was
executed. Fake gateways are used only in the public deterministic S11 integration test.

## S11 — structural reference matrix and deterministic end-to-end gate

`tests/fixtures/ap02/reference-test-matrix.json` defines contract
`ap02-structural-reference-matrix-v1` and maps every required T01-T34 reference intention to concrete
pytest functions. The architecture guard requires exactly the contiguous T01-T34 set and verifies
that every referenced test file/function exists. The HFT-style two-span case is explicit: an
introduction and list item remain separate anchors instead of becoming a mounted quote.

`tests/integration/context/test_ap02_source_bound_end_to_end.py` closes one public synthetic path
through the existing application boundaries:

```text
source resolution -> structural candidates -> bounded selection -> bound source package
-> fake extractor response -> current parser/common grounding -> fake verifier/cascade
-> proposal/package persistence -> existing clause-local evaluation
-> synthetic canonical-knowledge roundtrip -> existing formal projection -> source resolution
```

The fake gateways are deterministic in-process test doubles and make no network or model-server
call. The test uses synthetic accepted `DocumentKnowledge` only to exercise the existing canonical
roundtrip/projection path. It does not call or introduce an adoption service. Evaluation against the
synthetic expected result proves evaluator/grounding transport behavior only and is not a real-model
quality measurement.

A source-state regression test also proves that changing a parent heading invalidates reuse while an
unchanged target body alone is insufficient to preserve an old package.

## S12 — model-free context/evidence inspection

The application service contract `context-evidence-inspection-v1` composes existing source-package
selection/input binding and common grounding. Its report contains no source text. It exposes:

- target document/revision/clause/reference;
- candidate count and diagnostics;
- selected and omitted source identities, origins, structural paths, reasons and reach hints;
- explicit gaps and selection completeness;
- configured/used/remaining character budget;
- source-state, candidate-space, selection-decision and actual-input fingerprints plus package hash;
- one independent technical grounding result per supplied `EvidenceGroundingRequest`;
- invariant flags `model_execution: false` and `semantic_quality_assessed: false`.

The existing `context` CLI now exposes the thin read-only wrapper:

```bash
PYTHONPATH=src python -c 'from standards_atlas.cli import app; app()' \
  context evidence-inspect \
  --workspace tests/fixtures/ap02/context-evidence-inspection/workspace \
  --document-key AP02-SYNTH \
  --clause-id target \
  --grounding-requests tests/fixtures/ap02/context-evidence-inspection/grounding-requests.json \
  --character-budget 20000 \
  --max-sequence-distance 8 \
  --output /tmp/ap02-inspection.json
```

The public example deliberately contains two successful grounding requests and one failed request so
that the report shows independent success/failure rather than a misleading aggregate success claim.
A two-fresh-process integration test requires byte-identical JSON output with model/provider-related
environment variables removed. The persisted inspection JSON is text-free; private/source bytes stay
at their normal source boundary.

`docs/development/ap02-representability-matrix.md` maps the confirmed guide patterns (heading
definition, Safety-Plan context, HFT multi-span, separate Work Products, entity-only cases,
conditions/exceptions and Normative Force) to these technical tests. Synthetic structural/security
cases are listed separately and explicitly are not an AP03 Holdout.

## Private AP01 historical replay status

The real unchanged AP01 original audit and its associated private result files are **not present in
this supplied Series-E snapshot**. `local/` contains only `local/README.md` and
`local/sources/.gitkeep`. In particular, the documented original audit path is absent:

`local/review/assertions/assertion-pilot/0.1.0/assertion-review-pilot-v8-reviewed-complete.yaml`

The preserved expected SHA-256 for that original audit remains:

`eab6d6dfa30e7f5af2bb477f7c5bce19764d7f3459c403e27652ce6ff15d6fa1`

The associated private Golden/evaluation artifacts under `local/review/...` and
`local/evaluation/...` are absent as well. Therefore the requested **real historical offline replay
was not executed** and no real-pilot success is claimed. Nothing was reconstructed from summaries or
new context. Existing AP01 expected content, readable Golden IDs and historical bindings remain
untouched. The repository's public/synthetic AP01 offline-regression tests remain part of the S11/F
gates.

## AP03 handover

AP03 receives, without any new quality conclusion:

- frozen AP01 historical semantics plus the still-open status of the unavailable private replay;
- `source-bound-knowledge-proposal-request-v1` and
  `source-bound-knowledge-proposal-output-v1`;
- `source-bound-assertion-verifier-request-v1`;
- `context-source-package` schema 1 with the four source/input fingerprints;
- `ap02-structural-reference-matrix-v1` and its public synthetic reference fixtures;
- `context-evidence-inspection-v1` for deterministic diagnosis of exactly what a future experiment
  was given and what technically grounded;
- the constraint that successful grounding, fake-gateway agreement or synthetic evaluator exact
  match is not evidence of real extractor/verifier semantic quality.

Real model runs, prompt comparisons, Development/Holdout experiments and quality/release thresholds
start only in AP03 or later work explicitly assigned there.

## AP05 handover

AP05 receives the shared source model rather than an extractor-prompt representation: document and
surface identities, real origin/availability/access states, structural candidate paths, selected and
omitted excerpts, budget decisions, explicit gaps, media handles, package bindings and separate
source-state/candidate-space/selection/actual-input fingerprints. Retrieval may define its own
projection and budget policy while reusing these identities and access/invalidation rules. It is not
required to copy the full extractor context into retrieval text.

No AP05 retrieval/index implementation is included in Series F.

## Test status

The final executed commands and results are recorded in `_delivery/ap02-series-f/tests.md`. They
include the S11/S12 focused tests, the full T01-T34 mapped node set, the public two-fresh-process CLI
inspection, the source-bound end-to-end integration path and the widest practical regression gate in
this implementation environment. Ruff and repository-wide pytest status are reported there
separately; no incomplete or unavailable check is described as passed.

## AP02 closure boundary

AP02 now has a source-bound path in which structural candidate availability, bounded selection,
actual input, technical grounding, persisted evidence identity and post-projection source resolution
are distinguishable and inspectable. The visible result is provenance and reproducibility, not a new
semantic score. Private real-audit replay status remains a separately documented evidence gap rather
than being converted into a synthetic success.
