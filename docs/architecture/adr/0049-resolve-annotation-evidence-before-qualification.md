# ADR 0049: Resolve annotation evidence before qualification

## Status

Accepted

## Context

Semantic-role proposals must be compared with evidence of different maturity. Published
human reviews are reproducible Gold data, local reviews are authoritative but not yet
published, local proposals are Silver evidence, and EngineeringDocument structure can
provide a weaker deterministic baseline. Mixing these sources would hide coverage gaps
and make benchmark results irreproducible.

## Decision

Qualification resolves evidence per corpus clause using the priority
`published > local reviewed > local proposal > structure`. Gold metrics use only reviewed
or published annotations. Silver metrics use the highest-priority available evidence,
including proposals and structure fallbacks. Structure Agreement is reported separately.

Reports include multi-label precision, recall and F1, primary-role accuracy, exact match,
primary-role confusion, confidence calibration, coverage diagnostics, and breakdowns by
knowledge domain and corpus strata. Invalid or stale annotations are diagnosed rather
than silently ignored.

## Consequences

Model and prompt runs can be compared against a stable Gold subset while still using the
full corpus for Silver diagnostics. Coverage remains visible, and publication of additional
reviews automatically increases Gold eligibility without changing the metric contract.
