# AP01 status — Series B / S04–S06

Date: 2026-09-27. Series B implementation is complete in this delivery; user-local
`uv run ruff check .` and the uninterrupted full `uv run pytest` remain the acceptance
check after applying the delta. Series C/D are not implemented.

## Delivered boundaries

S04: strict multiset matching is separated from diagnostic/attribute alignment. Entity
recognition uses NFKC/casefold/collapsed-whitespace label identity; typed entities remain
a separate view. Assertion identity requires directed endpoints plus predicate. Duplicate
predictions stay visible and ambiguous buckets are never best-fit paired.

S05: report metrics now carry explicit numerator/denominator/value/status data. Entity and
typed-entity P/R/F1, class accuracy, assertion P/R/F1, predicate accuracy, normative-force
accuracy, over-/under-extraction and alignment coverage are computed from counts/supports.
Zero denominators produce `null`, and aggregate metrics are recomputed from aggregate
supports rather than averaged case percentages. The auto-adoption policy keeps typed
entity gates and uses the clean-break `min_evidence_span_exact_match_accuracy` threshold.

S06: frozen audit sources are resolved by document, clause and source kind. Own bodies and
headings, identifiable ancestor headings and complete associative-context bodies/headings
can be checked; missing surfaces are unavailable and conflicting frozen versions remain
explicit. Technical source integrity, exact golden-span equality and semantic evidence are
separate report dimensions. Clause-level exact match covers the fields actually annotated
in the golden and treats a missing candidate as missing, never as an exact empty result.

Current evaluation contract: `assertion-clause-local-v1`. Schema families remain at 1;
there is no reader for the Series-A interim report shape. Golden expectations, audit bytes,
productive context selection and model/prompt behavior were not changed. Work-product
metrics and semantic error findings remain Series C.

## Actual checks in this delivery environment

S04 matching/evaluation gate: 20 passed. S05 policy/CLI consumer gate: 16 passed.
S06 audit/source-resolution gate: 46 passed.
Assertion + CLI + assertion-architecture gate: 114 passed.
Assertion + CLI + assertion-architecture + schema gates: 208 passed.
Architecture + contract suite: 126 passed.
Integration subsets completed before the execution-window limit: adapters 32 passed / 1
skipped; application 1 passed; atlasdata 4 passed; knowledge 2 skipped; two workflow files
12 passed. A monolithic full-suite run and the slower enrichments workflow file exceeded
the container command window and are therefore not recorded as passes.

`uv run --offline ruff check .` could not resolve the project environment because
`jsonschema` is not present in the local uv cache while network access is disabled. Python
3.13 compilation and all completed pytest subsets above succeeded. This is an outstanding
lint/full-suite environment check, not a claimed Ruff/full-suite pass.

## Next authorized implementation boundary

After the user's local `ruff` and full `pytest` checks, Series C may implement S07-S08:
ontology-derived WorkProduct metrics and qualified error diagnoses. Do not change the
strict Series-B metrics to improve the v8 baseline, and do not start Series D or AP02/AP03
as part of a Series-B correction.
